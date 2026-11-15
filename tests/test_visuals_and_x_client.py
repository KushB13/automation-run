from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.config import Settings
from src.models import GeneratedPost, PostFormat, SourceType, SpecRow
from src.visuals.spec_card import render_spec_card
from src.x_client import XClient


def test_render_spec_card_grid_and_table(tmp_path: Path):
    grid_post = GeneratedPost(
        candidate_id="hf_model:Qwen/Qwen3-32B",
        source_type=SourceType.HUGGINGFACE_MODEL,
        post_format=PostFormat.SINGLE,
        tweets=["Check out Qwen3-32B"],
        reply_source_text="Source: https://huggingface.co/Qwen/Qwen3-32B",
        card_headline="Qwen/Qwen3-32B",
        card_subtitle="Open-weight 32.5B model trending on Hugging Face",
        card_specs=[
            SpecRow(label="Parameters", value="32.5B", highlight=True),
            SpecRow(label="Downloads (30d)", value="450.0K"),
            SpecRow(label="License", value="apache-2.0"),
        ],
        card_takeaway="Strong open-weight option for self-hosted reasoning.",
        source_url="https://huggingface.co/Qwen/Qwen3-32B",
    )
    grid_png = tmp_path / "grid.png"
    render_spec_card(grid_post, grid_png, x_handle="testbuilder")
    assert grid_png.exists()
    assert grid_png.stat().st_size > 20_000

    table_post = GeneratedPost(
        candidate_id="bench:newest",
        source_type=SourceType.MODEL_BENCHMARK,
        post_format=PostFormat.THREAD,
        tweets=["Tweet 1", "Tweet 2"],
        reply_source_text="Source: https://openrouter.ai/models",
        card_headline="Latest AI Model Specs & API Pricing",
        card_subtitle="Live context window and token pricing comparison",
        comparison_headers=["Model", "Context", "In /1M", "Out /1M"],
        comparison_rows=[
            ["Model A", "200K", "$3.00", "$15.0"],
            ["Model B", "1M", "$0.15", "$0.60"],
        ],
        card_takeaway="Context and output cost spread by 25x across tiers.",
        source_url="https://openrouter.ai/models",
    )
    table_png = tmp_path / "table.png"
    render_spec_card(table_post, table_png)
    assert table_png.exists()
    assert table_png.stat().st_size > 20_000


def test_x_client_publish_flow(tmp_path: Path):
    img = tmp_path / "card.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes")

    settings = Settings(
        X_API_KEY="k",
        X_API_SECRET="s",
        X_ACCESS_TOKEN="t",
        X_ACCESS_TOKEN_SECRET="ts",
    )
    client = XClient(settings)

    mock_session = MagicMock()

    def fake_post(url: str, **kwargs):
        resp = MagicMock()
        resp.ok = True
        if url.endswith("/media/upload/initialize"):
            resp.json.return_value = {"data": {"id": "media_999"}}
        elif url.endswith("/append"):
            resp.json.return_value = {}
        elif url.endswith("/finalize"):
            resp.json.return_value = {"data": {"id": "media_999"}}
        elif url.endswith("/tweets"):
            call_num = len(tweet_calls) + 1
            tweet_calls.append(kwargs["json"])
            resp.json.return_value = {"data": {"id": f"tweet_{call_num}"}}
        return resp

    tweet_calls = []
    mock_session.post.side_effect = fake_post
    client.session = mock_session

    post = GeneratedPost(
        candidate_id="gh:acme/test",
        source_type=SourceType.GITHUB_REPO,
        post_format=PostFormat.SINGLE,
        tweets=["Main tweet text"],
        reply_source_text="Source & full live specs: https://github.com/acme/test",
        card_headline="acme/test",
        card_subtitle="Test",
        source_url="https://github.com/acme/test",
    )

    ids = client.publish_post(post, [img])
    assert ids == ["tweet_1", "tweet_2"]
    assert tweet_calls[0]["media"] == {"media_ids": ["media_999"]}
    assert tweet_calls[1]["reply"] == {"in_reply_to_tweet_id": "tweet_1"}
