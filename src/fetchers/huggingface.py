from __future__ import annotations

import requests
from src.models import CandidateItem, SourceType, SpecRow

HF_MODELS_URL = "https://huggingface.co/api/models"
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
HEADERS = {"User-Agent": "ai-x-automation/0.1"}


def _format_params(total_params: int | float | None) -> str | None:
    if not total_params or total_params <= 0:
        return None
    if total_params >= 1e9:
        return f"{total_params / 1e9:.1f}B"
    if total_params >= 1e6:
        return f"{total_params / 1e6:.0f}M"
    return f"{int(total_params):,}"


def _format_count(n: int | float | None) -> str:
    if n is None:
        return "0"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fetch_trending_models(limit: int = 12, session: requests.Session | None = None) -> list[CandidateItem]:
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.headers.update(HEADERS)
    try:
        resp = session.get(
            HF_MODELS_URL,
            params={"sort": "trendingScore", "direction": "-1", "limit": limit, "full": "true"},
            timeout=20,
        )
        resp.raise_for_status()
        models = resp.json()
    finally:
        if own_session:
            session.close()

    items: list[CandidateItem] = []
    blocked_terms = ("uncensored", "heretic", "abliterated", "nsfw", "erotica")
    for m in models:
        model_id = m.get("id") or m.get("modelId")
        if not model_id:
            continue
        if any(term in model_id.lower() for term in blocked_terms):
            continue

        tags: list[str] = m.get("tags") or []
        license_tag = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
        arxiv_tag = next((t.split(":", 1)[1] for t in tags if t.startswith("arxiv:")), None)

        safetensors = m.get("safetensors") or {}
        total_params = safetensors.get("total")
        param_str = _format_params(total_params)

        downloads = m.get("downloads", 0) or 0
        likes = m.get("likes", 0) or 0
        trending_score = m.get("trendingScore", 0) or 0
        pipeline_tag = m.get("pipeline_tag") or "ai-model"
        library = m.get("library_name") or "transformers"
        author = m.get("author") or (model_id.split("/")[0] if "/" in model_id else "community")
        created_at = (m.get("createdAt") or "")[:10]

        specs: list[SpecRow] = [
            SpecRow(label="Task", value=pipeline_tag, highlight=True),
            SpecRow(label="Downloads (30d)", value=_format_count(downloads)),
            SpecRow(label="HF Likes", value=_format_count(likes)),
        ]
        if param_str:
            specs.insert(1, SpecRow(label="Parameters", value=param_str, highlight=True))
        if license_tag:
            specs.append(SpecRow(label="License", value=license_tag))
        if library:
            specs.append(SpecRow(label="Framework", value=library))
        if arxiv_tag:
            specs.append(SpecRow(label="Paper", value=f"arXiv:{arxiv_tag}"))
        if created_at:
            specs.append(SpecRow(label="Published", value=created_at))

        url = f"https://huggingface.co/{model_id}"
        summary_bits = [f"Trending {pipeline_tag} model by {author}"]
        if param_str:
            summary_bits.append(f"{param_str} parameters")
        if license_tag:
            summary_bits.append(f"{license_tag} license")
        summary_bits.append(f"{_format_count(downloads)} 30d downloads")

        items.append(
            CandidateItem(
                item_id=f"hf_model:{model_id}",
                source_type=SourceType.HUGGINGFACE_MODEL,
                title=model_id,
                url=url,
                summary=" · ".join(summary_bits) + ".",
                published_or_updated=created_at,
                popularity_score=float(trending_score) * 10 + float(likes),
                specs=specs,
                raw_metrics={
                    "model_id": model_id,
                    "author": author,
                    "downloads": downloads,
                    "likes": likes,
                    "trending_score": trending_score,
                    "parameters": param_str,
                    "license": license_tag,
                    "pipeline_tag": pipeline_tag,
                    "library": library,
                },
                screenshot_url=url,
            )
        )
    return items


def fetch_daily_papers(limit: int = 10, session: requests.Session | None = None) -> list[CandidateItem]:
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.headers.update(HEADERS)
    try:
        resp = session.get(HF_DAILY_PAPERS_URL, timeout=20)
        resp.raise_for_status()
        papers = resp.json()
    finally:
        if own_session:
            session.close()

    items: list[CandidateItem] = []
    for entry in papers[:limit]:
        paper = entry.get("paper") or {}
        paper_id = paper.get("id")
        title = (paper.get("title") or "").strip()
        if not paper_id or not title:
            continue

        summary = (paper.get("summary") or "").strip().replace("\n", " ")
        upvotes = paper.get("upvotes", 0) or 0
        authors = paper.get("authors") or []
        published_at = (paper.get("publishedAt") or "")[:10]
        github_repo = paper.get("githubRepo") or ""
        github_stars = paper.get("githubStars")

        specs: list[SpecRow] = [
            SpecRow(label="arXiv ID", value=paper_id, highlight=True),
            SpecRow(label="HF Upvotes", value=str(upvotes), highlight=True),
            SpecRow(label="Authors", value=str(len(authors)) if authors else "N/A"),
        ]
        if published_at:
            specs.append(SpecRow(label="Published", value=published_at))
        if github_repo:
            repo_short = github_repo.replace("https://github.com/", "").strip("/")
            specs.append(SpecRow(label="Code Repo", value=repo_short))
        if github_stars is not None:
            specs.append(SpecRow(label="GitHub Stars", value=_format_count(github_stars)))

        url = f"https://huggingface.co/papers/{paper_id}"
        items.append(
            CandidateItem(
                item_id=f"hf_paper:{paper_id}",
                source_type=SourceType.HUGGINGFACE_PAPER,
                title=title,
                url=url,
                summary=summary[:700],
                published_or_updated=published_at,
                popularity_score=float(upvotes) * 5 + (float(github_stars or 0) * 0.05),
                specs=specs,
                raw_metrics={
                    "paper_id": paper_id,
                    "upvotes": upvotes,
                    "author_count": len(authors),
                    "github_repo": github_repo,
                    "github_stars": github_stars,
                    "published_at": published_at,
                },
                screenshot_url=url,
            )
        )
    return items
