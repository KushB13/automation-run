from __future__ import annotations

import logging
import mimetypes
import time
from pathlib import Path
import requests
from requests_oauthlib import OAuth1

from src.config import Settings
from src.models import GeneratedPost, PostFormat

logger = logging.getLogger(__name__)

X_API_BASE = "https://api.x.com/2"
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB (< 5 MB X API limit)


class XApiError(RuntimeError):
    """Raised when an X API v2 call fails."""


class XClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.auth = OAuth1(
            client_key=settings.x_api_key,
            client_secret=settings.x_api_secret,
            resource_owner_key=settings.x_access_token,
            resource_owner_secret=settings.x_access_token_secret,
        )
        self.session = requests.Session()
        self.session.auth = self.auth

    def upload_image(self, image_path: Path) -> str:
        """Upload an image using the X API v2 chunked media endpoints and return media_id."""
        if not image_path.exists():
            raise FileNotFoundError(f"Media file not found: {image_path}")

        data = image_path.read_bytes()
        total_bytes = len(data)
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            mime_type = "image/png"

        # Step 1: Initialize
        init_resp = self.session.post(
            f"{X_API_BASE}/media/upload/initialize",
            json={
                "media_type": mime_type,
                "total_bytes": total_bytes,
                "media_category": "tweet_image",
            },
            timeout=30,
        )
        if not init_resp.ok:
            raise XApiError(f"Media initialize failed ({init_resp.status_code}): {init_resp.text}")

        media_id = (init_resp.json().get("data") or {}).get("id")
        if not media_id:
            raise XApiError(f"Missing media_id in initialize response: {init_resp.text}")

        # Step 2: Append chunks
        for idx, offset in enumerate(range(0, total_bytes, CHUNK_SIZE)):
            chunk = data[offset : offset + CHUNK_SIZE]
            append_resp = self.session.post(
                f"{X_API_BASE}/media/upload/{media_id}/append",
                data={"segment_index": str(idx)},
                files={"media": (image_path.name, chunk, mime_type)},
                timeout=60,
            )
            if not append_resp.ok:
                raise XApiError(
                    f"Media append failed on chunk {idx} ({append_resp.status_code}): {append_resp.text}"
                )

        # Step 3: Finalize
        fin_resp = self.session.post(
            f"{X_API_BASE}/media/upload/{media_id}/finalize",
            timeout=30,
        )
        if not fin_resp.ok:
            raise XApiError(f"Media finalize failed ({fin_resp.status_code}): {fin_resp.text}")

        fin_data = fin_resp.json().get("data") or {}
        processing_info = fin_data.get("processing_info")
        while processing_info and processing_info.get("state") in {"pending", "in_progress"}:
            wait_secs = min(int(processing_info.get("check_after_secs", 2)), 10)
            time.sleep(wait_secs)
            status_resp = self.session.get(
                f"{X_API_BASE}/media/upload",
                params={"command": "STATUS", "media_id": media_id},
                timeout=30,
            )
            if not status_resp.ok:
                raise XApiError(
                    f"Media status poll failed ({status_resp.status_code}): {status_resp.text}"
                )
            processing_info = (status_resp.json().get("data") or {}).get("processing_info")
            if processing_info and processing_info.get("state") == "failed":
                raise XApiError(f"Media processing failed: {processing_info}")

        return str(media_id)

    def create_tweet(
        self,
        text: str,
        media_ids: list[str] | None = None,
        reply_to_id: str | None = None,
    ) -> str:
        payload: dict = {"text": text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        resp = self.session.post(f"{X_API_BASE}/tweets", json=payload, timeout=30)
        if not resp.ok:
            raise XApiError(f"create_tweet failed ({resp.status_code}): {resp.text}")

        tweet_id = (resp.json().get("data") or {}).get("id")
        if not tweet_id:
            raise XApiError(f"Missing tweet id in response: {resp.text}")
        return str(tweet_id)

    def publish_post(
        self,
        post: GeneratedPost,
        media_paths: list[Path],
    ) -> list[str]:
        """Publish single post or thread + auto-reply source link. Returns created tweet IDs."""
        valid_paths = [p for p in media_paths if p and p.exists()][:4]
        media_ids = [self.upload_image(p) for p in valid_paths]

        created_ids: list[str] = []
        parent_id: str | None = None

        for idx, tweet_text in enumerate(post.tweets):
            if post.post_format == PostFormat.THREAD and len(media_ids) >= 2 and idx in (0, 1):
                tweet_media = [media_ids[idx]]
            elif idx == 0:
                tweet_media = media_ids
            else:
                tweet_media = None

            tid = self.create_tweet(
                text=tweet_text,
                media_ids=tweet_media,
                reply_to_id=parent_id,
            )
            created_ids.append(tid)
            parent_id = tid
            time.sleep(1.0)

        # Auto-reply with clean source URL so main tweet retains full X reach
        if post.reply_source_text and parent_id:
            reply_id = self.create_tweet(
                text=post.reply_source_text,
                reply_to_id=parent_id,
            )
            created_ids.append(reply_id)

        return created_ids
