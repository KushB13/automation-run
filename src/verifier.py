from __future__ import annotations

import re
from src.models import GeneratedPost, PostFormat

URL_PATTERN = re.compile(r"https?://\S+")
HASHTAG_PATTERN = re.compile(r"(?<!\w)#\w+")


def count_x_chars(text: str) -> int:
    """Compute X-weighted tweet length (URLs count as 23 chars on X)."""
    def _replace_url(match: re.Match[str]) -> str:
        return "x" * 23

    normalized = URL_PATTERN.sub(_replace_url, text)
    return len(normalized)


def _strip_hashtag_spam(text: str) -> str:
    cleaned = HASHTAG_PATTERN.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _truncate_to_limit(text: str, max_chars: int) -> str:
    if count_x_chars(text) <= max_chars:
        return text
    # Try dropping trailing lines or words cleanly
    lines = text.splitlines()
    while len(lines) > 1 and count_x_chars("\n".join(lines)) > max_chars:
        lines.pop()
    candidate = "\n".join(lines).strip()
    if count_x_chars(candidate) <= max_chars and candidate:
        return candidate

    words = text.split()
    while len(words) > 1 and count_x_chars(" ".join(words) + "...") > max_chars:
        words.pop()
    trimmed = (" ".join(words) + "...").strip()
    if count_x_chars(trimmed) <= max_chars:
        return trimmed
    return text[: max_chars - 3].rstrip() + "..."


def verify_and_sanitize_post(post: GeneratedPost, max_chars: int = 280) -> GeneratedPost:
    """Enforce X character limits, clean formatting, and zero hashtag spam."""
    cleaned_tweets: list[str] = []
    for raw in post.tweets:
        t = _strip_hashtag_spam(raw)
        if not t:
            continue
        t = _truncate_to_limit(t, max_chars)
        cleaned_tweets.append(t)

    if not cleaned_tweets:
        fallback = _truncate_to_limit(f"{post.card_headline} — {post.card_subtitle}", max_chars)
        cleaned_tweets = [fallback]

    if post.post_format == PostFormat.SINGLE and len(cleaned_tweets) > 1:
        cleaned_tweets = [cleaned_tweets[0]]
    elif post.post_format == PostFormat.THREAD and len(cleaned_tweets) > 3:
        cleaned_tweets = cleaned_tweets[:3]

    post.tweets = cleaned_tweets
    post.reply_source_text = _truncate_to_limit(post.reply_source_text.strip(), max_chars)
    return post
