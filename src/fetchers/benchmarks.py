from __future__ import annotations

from datetime import datetime, timezone
import requests
from src.models import CandidateItem, SourceType, SpecRow

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
HEADERS = {"User-Agent": "ai-x-automation/0.1"}


def _per_million_price(per_token_str: str | float | None) -> str:
    if per_token_str is None:
        return "N/A"
    try:
        val = float(per_token_str) * 1_000_000
    except (TypeError, ValueError):
        return "N/A"
    if val <= 0:
        return "Free"
    if val < 0.1:
        return f"${val:.3f}"
    if val < 10:
        return f"${val:.2f}"
    return f"${val:.1f}"


def _format_context(ctx: int | None) -> str:
    if not ctx or ctx <= 0:
        return "N/A"
    if ctx >= 1_000_000:
        m = round(ctx / 1_000_000, 1)
        return f"{int(m)}M" if m == int(m) else f"{m:.1f}M"
    if ctx >= 1_000:
        return f"{ctx // 1_000}K"
    return str(ctx)


def _short_model_name(name: str, model_id: str) -> str:
    clean = name.split(":", 1)[-1].strip() if ":" in name else name.strip()
    if len(clean) > 30:
        clean = clean[:27].rstrip() + "..."
    return clean or model_id


def fetch_model_benchmarks(session: requests.Session | None = None) -> list[CandidateItem]:
    """Fetch live model pricing, context window, and modality specs to build real comparison tables."""
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.headers.update(HEADERS)
    try:
        resp = session.get(OPENROUTER_MODELS_URL, timeout=20)
        resp.raise_for_status()
        models = resp.json().get("data") or []
    finally:
        if own_session:
            session.close()

    filtered = []
    for m in models:
        mid = m.get("id") or ""
        if not mid or mid.endswith(":free") or mid.endswith(":extended") or "auto" in mid:
            continue
        pricing = m.get("pricing") or {}
        try:
            prompt_p = float(pricing.get("prompt", -1))
            comp_p = float(pricing.get("completion", -1))
        except (TypeError, ValueError):
            continue
        if prompt_p < 0 or comp_p < 0:
            continue
        ctx = m.get("context_length") or 0
        if ctx < 32_000:
            continue
        filtered.append(m)

    filtered.sort(key=lambda m: m.get("created") or 0, reverse=True)
    today_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    candidates: list[CandidateItem] = []

    newest_distinct: list[dict] = []
    seen_providers: set[str] = set()
    for m in filtered:
        provider = m["id"].split("/")[0]
        if provider in seen_providers and len(newest_distinct) < 4:
            continue
        seen_providers.add(provider)
        newest_distinct.append(m)
        if len(newest_distinct) >= 5:
            break

    if len(newest_distinct) >= 3:
        rows = []
        raw_models = []
        for m in newest_distinct:
            pricing = m.get("pricing") or {}
            top_prov = m.get("top_provider") or {}
            arch = m.get("architecture") or {}
            in_p = _per_million_price(pricing.get("prompt"))
            out_p = _per_million_price(pricing.get("completion"))
            ctx = _format_context(m.get("context_length"))
            max_out = _format_context(top_prov.get("max_completion_tokens"))
            modality = arch.get("modality") or "text->text"
            name = _short_model_name(m.get("name") or m["id"], m["id"])
            rows.append([name, ctx, max_out, in_p, out_p, modality])
            raw_models.append(
                {
                    "id": m["id"],
                    "name": name,
                    "context": ctx,
                    "max_output": max_out,
                    "input_per_1m": in_p,
                    "output_per_1m": out_p,
                    "modality": modality,
                }
            )

        candidates.append(
            CandidateItem(
                item_id=f"bench:newest-releases:{today_tag}",
                source_type=SourceType.MODEL_BENCHMARK,
                title=f"Latest AI Model Specs & API Pricing ({today_tag})",
                url="https://openrouter.ai/models",
                summary="Side-by-side live context window, max output, and API token pricing for the newest released AI models.",
                published_or_updated=today_tag,
                popularity_score=900.0,
                specs=[
                    SpecRow(label="Models Compared", value=str(len(rows)), highlight=True),
                    SpecRow(label="Data Source", value="OpenRouter Live Catalog"),
                    SpecRow(label="Metrics", value="Context / Max Out / $/1M"),
                ],
                comparison_headers=["Model", "Context", "Max Out", "In /1M", "Out /1M", "Modality"],
                comparison_rows=rows,
                raw_metrics={"models": raw_models, "snapshot_date": today_tag},
                screenshot_url="https://openrouter.ai/rankings",
            )
        )

    long_ctx = [
        m for m in filtered[:80]
        if (m.get("context_length") or 0) >= 200_000 and float((m.get("pricing") or {}).get("completion", 0)) > 0
    ]
    long_ctx.sort(key=lambda m: float((m.get("pricing") or {}).get("completion", 999)))
    if len(long_ctx) >= 4:
        top_value = long_ctx[:5]
        rows = []
        raw_models = []
        for m in top_value:
            pricing = m.get("pricing") or {}
            top_prov = m.get("top_provider") or {}
            in_p = _per_million_price(pricing.get("prompt"))
            out_p = _per_million_price(pricing.get("completion"))
            ctx = _format_context(m.get("context_length"))
            max_out = _format_context(top_prov.get("max_completion_tokens"))
            name = _short_model_name(m.get("name") or m["id"], m["id"])
            rows.append([name, ctx, max_out, in_p, out_p])
            raw_models.append(
                {
                    "id": m["id"],
                    "name": name,
                    "context": ctx,
                    "max_output": max_out,
                    "input_per_1m": in_p,
                    "output_per_1m": out_p,
                }
            )
        candidates.append(
            CandidateItem(
                item_id=f"bench:long-context-value:{today_tag}",
                source_type=SourceType.MODEL_BENCHMARK,
                title=f"Cheapest 200K+ Context AI Models Right Now ({today_tag})",
                url="https://openrouter.ai/models",
                summary="Live comparison of recent >=200K context window AI models ranked by lowest output token pricing.",
                published_or_updated=today_tag,
                popularity_score=850.0,
                specs=[
                    SpecRow(label="Context Floor", value="200K+ tokens", highlight=True),
                    SpecRow(label="Models Compared", value=str(len(rows))),
                    SpecRow(label="Sorted By", value="Lowest Output $/1M"),
                ],
                comparison_headers=["Model", "Context", "Max Out", "In /1M", "Out /1M"],
                comparison_rows=rows,
                raw_metrics={"models": raw_models, "snapshot_date": today_tag},
                screenshot_url="https://openrouter.ai/rankings",
            )
        )

    return candidates
