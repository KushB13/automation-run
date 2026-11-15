from __future__ import annotations

from datetime import datetime, timedelta, timezone
import requests
from src.models import CandidateItem, SourceType, SpecRow

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def _format_count(n: int | None) -> str:
    if not n:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fetch_trending_ai_repos(
    limit: int = 12,
    github_token: str = "",
    session: requests.Session | None = None,
) -> list[CandidateItem]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-x-automation/0.1",
    }
    if github_token.strip():
        headers["Authorization"] = f"Bearer {github_token.strip()}"

    cutoff_new = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    cutoff_active = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    queries = [
        f"created:>={cutoff_new} topic:ai stars:>100 forks:>15",
        f"pushed:>={cutoff_active} topic:llm stars:>1500 forks:>50",
        f"pushed:>={cutoff_active} topic:ai-agents stars:>1000 forks:>30",
    ]

    own_session = session is None
    if own_session:
        session = requests.Session()

    seen_full_names: set[str] = set()
    seen_repo_names: set[str] = set()
    items: list[CandidateItem] = []

    try:
        for q_idx, q in enumerate(queries):
            resp = session.get(
                GITHUB_SEARCH_URL,
                params={"q": q, "sort": "stars", "order": "desc", "per_page": limit},
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            repos = resp.json().get("items") or []

            for r in repos:
                full_name = r.get("full_name")
                repo_name = (r.get("name") or "").lower()
                if not full_name or full_name in seen_full_names or repo_name in seen_repo_names:
                    continue
                seen_full_names.add(full_name)
                if repo_name:
                    seen_repo_names.add(repo_name)

                stars = r.get("stargazers_count", 0) or 0
                forks = r.get("forks_count", 0) or 0
                issues = r.get("open_issues_count", 0) or 0
                language = r.get("language") or "Multi"
                license_info = r.get("license") or {}
                license_spdx = license_info.get("spdx_id") or "N/A"
                if license_spdx == "NOASSERTION":
                    license_spdx = "Custom"
                description = (r.get("description") or "").strip()
                topics = r.get("topics") or []
                created_at = (r.get("created_at") or "")[:10]
                pushed_at = (r.get("pushed_at") or "")[:10]
                html_url = r.get("html_url") or f"https://github.com/{full_name}"

                velocity_bonus = 3.0 if q_idx == 0 else 0.25
                popularity = float(stars) * velocity_bonus

                specs: list[SpecRow] = [
                    SpecRow(label="Stars", value=_format_count(stars), highlight=True),
                    SpecRow(label="Forks", value=_format_count(forks)),
                    SpecRow(label="Language", value=language, highlight=True),
                    SpecRow(label="License", value=license_spdx),
                    SpecRow(label="Created", value=created_at),
                    SpecRow(label="Last Push", value=pushed_at),
                ]
                if topics:
                    specs.append(SpecRow(label="Topics", value=", ".join(topics[:4])))

                items.append(
                    CandidateItem(
                        item_id=f"gh:{full_name}",
                        source_type=SourceType.GITHUB_REPO,
                        title=full_name,
                        url=html_url,
                        summary=f"{description} (Stars: {stars:,}, Forks: {forks:,}, Language: {language}, License: {license_spdx})",
                        published_or_updated=pushed_at or created_at,
                        popularity_score=popularity,
                        specs=specs,
                        raw_metrics={
                            "full_name": full_name,
                            "stars": stars,
                            "forks": forks,
                            "open_issues": issues,
                            "language": language,
                            "license": license_spdx,
                            "created_at": created_at,
                            "pushed_at": pushed_at,
                            "topics": topics[:6],
                        },
                        screenshot_url=html_url,
                    )
                )
    finally:
        if own_session:
            session.close()

    items.sort(key=lambda x: x.popularity_score, reverse=True)
    return items[:limit]
