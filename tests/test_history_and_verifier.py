from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.history import (
    filter_unseen_candidates,
    load_history,
    recent_source_penalties,
    save_history,
)
from src.models import CandidateItem, GeneratedPost, HistoryEntry, PostFormat, SourceType
from src.verifier import count_x_chars, verify_and_sanitize_post


def test_history_dedup_and_rotation(tmp_path: Path):
    hist_path = tmp_path / "history.json"
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)

    entries = [
        HistoryEntry(
            item_id="gh:old/repo",
            source_type=SourceType.GITHUB_REPO,
            title="old/repo",
            url="https://github.com/old/repo",
            post_format=PostFormat.SINGLE,
            tweets=["old tweet"],
            tweet_ids=["1"],
            posted_at=old.isoformat(),
        ),
        HistoryEntry(
            item_id="hf_model:recent/model",
            source_type=SourceType.HUGGINGFACE_MODEL,
            title="recent/model",
            url="https://huggingface.co/recent/model",
            post_format=PostFormat.SINGLE,
            tweets=["recent tweet"],
            tweet_ids=["2"],
            posted_at=now.isoformat(),
        ),
    ]
    save_history(hist_path, entries)
    loaded = load_history(hist_path)
    assert len(loaded) == 2

    candidates = [
        CandidateItem(
            item_id="gh:old/repo",
            source_type=SourceType.GITHUB_REPO,
            title="old/repo",
            url="https://github.com/old/repo",
            summary="Old enough to revisit",
        ),
        CandidateItem(
            item_id="hf_model:recent/model",
            source_type=SourceType.HUGGINGFACE_MODEL,
            title="recent/model",
            url="https://huggingface.co/recent/model",
            summary="Posted today, should be filtered",
        ),
    ]

    unseen = filter_unseen_candidates(candidates, loaded, cooldown_days=30)
    assert [c.item_id for c in unseen] == ["gh:old/repo"]

    penalties = recent_source_penalties(loaded, lookback=4)
    assert penalties[SourceType.HUGGINGFACE_MODEL] > penalties[SourceType.MODEL_BENCHMARK]


def test_verifier_strips_hashtags_and_enforces_280():
    long_text = "AI update: " + ("word " * 80) + "#AI #MachineLearning"
    post = GeneratedPost(
        candidate_id="gh:acme/test",
        source_type=SourceType.GITHUB_REPO,
        post_format=PostFormat.SINGLE,
        tweets=[long_text, "extra tweet that single should drop"],
        reply_source_text="Source: https://github.com/acme/test",
        card_headline="acme/test",
        card_subtitle="Fast AI tool",
        source_url="https://github.com/acme/test",
    )

    verified = verify_and_sanitize_post(post, max_chars=280)
    assert len(verified.tweets) == 1
    assert "#" not in verified.tweets[0]
    assert count_x_chars(verified.tweets[0]) <= 280
    assert count_x_chars(verified.reply_source_text) <= 280
