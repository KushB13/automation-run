from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.config import Settings
from src.curator import curate_and_generate_post
from src.fetchers import fetch_all_candidates
from src.history import (
    filter_unseen_candidates,
    load_history,
    recent_source_penalties,
    save_history,
)
from src.models import HistoryEntry
from src.verifier import count_x_chars, verify_and_sanitize_post
from src.visuals.live_capture import capture_live_webpage
from src.visuals.spec_card import render_spec_card
from src.x_client import XClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ai_x_bot")


def run(settings: Settings | None = None) -> int:
    settings = settings or Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    history = load_history(settings.history_path)
    candidates = fetch_all_candidates(settings)
    if not candidates:
        raise RuntimeError("No candidates fetched from any source.")

    unseen = filter_unseen_candidates(
        candidates, history, cooldown_days=settings.dedup_cooldown_days
    )
    if not unseen:
        logger.warning("All fetched candidates were recently posted; reusing full candidate pool.")
        unseen = candidates

    penalties = recent_source_penalties(history)
    post = curate_and_generate_post(unseen, penalties, settings)
    post = verify_and_sanitize_post(post, max_chars=settings.max_tweet_chars)

    chosen_candidate = next((c for c in unseen if c.item_id == post.candidate_id), unseen[0])

    # Render crisp real-data spec card + capture live webpage screenshot (zero AI-generated images)
    spec_card_path = settings.output_dir / "spec_card.png"
    render_spec_card(post, spec_card_path, x_handle=settings.x_handle)

    live_shot_path: Path | None = None
    if chosen_candidate.screenshot_url:
        live_shot_path = capture_live_webpage(
            chosen_candidate.screenshot_url,
            settings.output_dir / "live_shot.png",
        )

    media_paths = [spec_card_path]
    if live_shot_path:
        media_paths.append(live_shot_path)

    logger.info("Selected candidate: %s (%s)", chosen_candidate.title, chosen_candidate.source_type.value)
    logger.info("Post format: %s | Screenshots: %s", post.post_format.value, [str(p) for p in media_paths])
    for idx, t in enumerate(post.tweets, start=1):
        logger.info("Tweet %d (%d/%d chars):\n%s", idx, count_x_chars(t), settings.max_tweet_chars, t)
    logger.info("Auto-reply source: %s", post.reply_source_text)

    if settings.dry_run:
        logger.info("DRY_RUN=true — skipping X API publish.")
        tweet_ids: list[str] = []
    else:
        if not settings.has_x_credentials:
            raise RuntimeError(
                "Missing X API credentials (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET). "
                "Set DRY_RUN=true to test locally without posting."
            )
        client = XClient(settings)
        tweet_ids = client.publish_post(post, media_paths)
        logger.info("Published to X successfully! Tweet IDs: %s", tweet_ids)

    if not settings.dry_run:
        history.append(
            HistoryEntry(
                item_id=post.candidate_id,
                source_type=post.source_type,
                title=chosen_candidate.title,
                url=post.source_url,
                post_format=post.post_format,
                tweets=post.tweets,
                tweet_ids=tweet_ids,
                posted_at=datetime.now(timezone.utc).isoformat(),
                dry_run=False,
            )
        )
        save_history(settings.history_path, history)
        logger.info("Saved updated history to %s", settings.history_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
