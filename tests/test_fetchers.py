from __future__ import annotations

from unittest.mock import MagicMock

from src.fetchers.benchmarks import fetch_model_benchmarks
from src.fetchers.github_ai import fetch_trending_ai_repos
from src.fetchers.huggingface import fetch_daily_papers, fetch_trending_models
from src.models import SourceType


def _mock_session(payload: dict | list) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    session = MagicMock()
    session.get.return_value = resp
    return session


def test_fetch_trending_models():
    session = _mock_session(
        [
            {
                "id": "Qwen/Qwen3-32B",
                "author": "Qwen",
                "pipeline_tag": "text-generation",
                "downloads": 450000,
                "likes": 1200,
                "trendingScore": 85,
                "library_name": "transformers",
                "createdAt": "2026-11-01T10:00:00.000Z",
                "tags": ["license:apache-2.0", "arxiv:2505.00001"],
                "safetensors": {"total": 32_500_000_000},
            }
        ]
    )

    items = fetch_trending_models(limit=5, session=session)
    assert len(items) == 1
    item = items[0]
    assert item.item_id == "hf_model:Qwen/Qwen3-32B"
    assert item.source_type == SourceType.HUGGINGFACE_MODEL
    assert item.url == "https://huggingface.co/Qwen/Qwen3-32B"
    spec_map = {s.label: s.value for s in item.specs}
    assert spec_map["Parameters"] == "32.5B"
    assert spec_map["License"] == "apache-2.0"
    assert spec_map["Downloads (30d)"] == "450.0K"


def test_fetch_daily_papers():
    session = _mock_session(
        [
            {
                "paper": {
                    "id": "2611.01234",
                    "title": "Efficient Reasoning Distillation",
                    "summary": "We show smaller models match frontier math accuracy.",
                    "upvotes": 74,
                    "authors": [{"name": "Alice"}, {"name": "Bob"}],
                    "publishedAt": "2026-11-14T00:00:00.000Z",
                    "githubRepo": "https://github.com/org/reason-distill",
                    "githubStars": 1850,
                }
            }
        ]
    )

    items = fetch_daily_papers(limit=5, session=session)
    assert len(items) == 1
    item = items[0]
    assert item.item_id == "hf_paper:2611.01234"
    assert item.source_type == SourceType.HUGGINGFACE_PAPER
    spec_map = {s.label: s.value for s in item.specs}
    assert spec_map["HF Upvotes"] == "74"
    assert spec_map["Code Repo"] == "org/reason-distill"


def test_fetch_trending_ai_repos():
    session = _mock_session(
        {
            "items": [
                {
                    "full_name": "acme/agent-sandbox",
                    "stargazers_count": 3420,
                    "forks_count": 210,
                    "open_issues_count": 15,
                    "language": "Python",
                    "license": {"spdx_id": "MIT"},
                    "description": "Fast local sandbox for coding agents.",
                    "topics": ["ai-agents", "llm", "python"],
                    "created_at": "2026-11-10T00:00:00Z",
                    "pushed_at": "2026-11-15T00:00:00Z",
                    "html_url": "https://github.com/acme/agent-sandbox",
                }
            ]
        }
    )

    items = fetch_trending_ai_repos(limit=5, session=session)
    assert len(items) == 1
    item = items[0]
    assert item.item_id == "gh:acme/agent-sandbox"
    assert item.source_type == SourceType.GITHUB_REPO
    spec_map = {s.label: s.value for s in item.specs}
    assert spec_map["Stars"] == "3.4K"
    assert spec_map["License"] == "MIT"


def test_fetch_model_benchmarks():
    session = _mock_session(
        {
            "data": [
                {
                    "id": "anthropic/claude-test",
                    "name": "Anthropic: Claude Test",
                    "created": 1763000000,
                    "context_length": 200000,
                    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                    "architecture": {"modality": "text+image->text"},
                    "top_provider": {"max_completion_tokens": 64000},
                },
                {
                    "id": "openai/gpt-test",
                    "name": "OpenAI: GPT Test",
                    "created": 1762900000,
                    "context_length": 128000,
                    "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                    "architecture": {"modality": "text+image->text"},
                    "top_provider": {"max_completion_tokens": 32000},
                },
                {
                    "id": "google/gemini-test",
                    "name": "Google: Gemini Test",
                    "created": 1762800000,
                    "context_length": 1000000,
                    "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                    "architecture": {"modality": "text+image->text"},
                    "top_provider": {"max_completion_tokens": 65536},
                },
                {
                    "id": "qwen/qwen-test",
                    "name": "Qwen: Qwen Test",
                    "created": 1762700000,
                    "context_length": 262144,
                    "pricing": {"prompt": "0.0000002", "completion": "0.0000008"},
                    "architecture": {"modality": "text->text"},
                    "top_provider": {"max_completion_tokens": 32768},
                },
            ]
        }
    )

    items = fetch_model_benchmarks(session=session)
    assert len(items) >= 1
    bench = items[0]
    assert bench.source_type == SourceType.MODEL_BENCHMARK
    assert bench.comparison_headers == ["Model", "Context", "Max Out", "In /1M", "Out /1M", "Modality"]
    assert len(bench.comparison_rows) == 4
    assert bench.comparison_rows[0][0] == "Claude Test"
    assert bench.comparison_rows[0][3] == "$3.00"
    assert bench.comparison_rows[0][4] == "$15.0"
