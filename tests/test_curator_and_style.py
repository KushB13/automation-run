from __future__ import annotations

from pathlib import Path

from src.config import Settings
from src.curator import curate_and_generate_post, load_style_examples
from src.models import CandidateItem, PostFormat, SourceType, SpecRow
from src.verifier import count_x_chars, verify_and_sanitize_post


def test_load_default_style_examples():
    cfg = load_style_examples(Path("data/style_examples.json"))
    assert len(cfg["voice_notes"]) >= 2
    assert len(cfg["examples"]) >= 3
    assert all("tweets" in ex for ex in cfg["examples"])


def test_curate_ai_news_fallback_single_and_thread():
    candidate = CandidateItem(
        item_id="ai_news:abc123",
        source_type=SourceType.AI_NEWS,
        title="OpenAI releases native tracing and faster agent runtime",
        url="https://openai.com/news/agent-runtime",
        summary=(
            "Tool-calling latency drops across structured outputs. "
            "Built-in tracing removes external wrapper boilerplate for production devs."
        ),
        published_or_updated="2026-11-15",
        popularity_score=850.0,
        specs=[
            SpecRow(label="Source", value="OpenAI News", highlight=True),
            SpecRow(label="Category", value="Lab Announcement", highlight=True),
            SpecRow(label="Freshness", value="2h ago"),
        ],
        raw_metrics={"publisher": "OpenAI News"},
    )

    single_post = curate_and_generate_post(
        [candidate],
        {s: 0 for s in SourceType},
        Settings(GEMINI_API_KEY="", POST_FORMAT_OVERRIDE="single"),
    )
    single_post = verify_and_sanitize_post(single_post, max_chars=280)
    assert single_post.post_format == PostFormat.SINGLE
    assert len(single_post.tweets) == 1
    assert count_x_chars(single_post.tweets[0]) <= 280
    assert len(single_post.card_bullets) >= 1

    thread_post = curate_and_generate_post(
        [candidate],
        {s: 0 for s in SourceType},
        Settings(GEMINI_API_KEY="", POST_FORMAT_OVERRIDE="thread"),
    )
    thread_post = verify_and_sanitize_post(thread_post, max_chars=280)
    assert thread_post.post_format == PostFormat.THREAD
    assert len(thread_post.tweets) == 2
    assert all(count_x_chars(t) <= 280 for t in thread_post.tweets)
