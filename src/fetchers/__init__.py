from __future__ import annotations

import logging
from src.config import Settings
from src.models import CandidateItem, SourceType
from src.fetchers.huggingface import fetch_trending_models, fetch_daily_papers
from src.fetchers.github_ai import fetch_trending_ai_repos
from src.fetchers.benchmarks import fetch_model_benchmarks

logger = logging.getLogger(__name__)


def fetch_all_candidates(settings: Settings) -> list[CandidateItem]:
    """Fetch fresh real-data candidates from all enabled AI sources."""
    override = (settings.source_override or "auto").strip().lower()
    candidates: list[CandidateItem] = []

    fetchers: list[tuple[SourceType, callable]] = [
        (SourceType.HUGGINGFACE_MODEL, lambda: fetch_trending_models()),
        (SourceType.HUGGINGFACE_PAPER, lambda: fetch_daily_papers()),
        (SourceType.GITHUB_REPO, lambda: fetch_trending_ai_repos(github_token=settings.github_token)),
        (SourceType.MODEL_BENCHMARK, lambda: fetch_model_benchmarks()),
    ]

    for source_type, fn in fetchers:
        if override != "auto" and override != source_type.value:
            continue
        try:
            items = fn()
            logger.info("Fetched %d candidates from %s", len(items), source_type.value)
            candidates.extend(items)
        except Exception as exc:
            logger.warning("Failed fetching from %s: %s", source_type.value, exc)

    return candidates
