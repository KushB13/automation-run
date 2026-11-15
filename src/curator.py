from __future__ import annotations

import json
import logging
from pathlib import Path
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src.config import Settings
from src.models import CandidateItem, GeneratedPost, PostFormat, SourceType

logger = logging.getLogger(__name__)


class _CuratedOutput(BaseModel):
    selected_item_id: str = Field(description="Exact item_id from the candidate list.")
    post_format: str = Field(description="Either 'single' or 'thread'.")
    tweets: list[str] = Field(
        description=(
            "1 tweet if post_format=='single', or 2-3 tweets if post_format=='thread'. "
            "Every tweet MUST be <= 265 characters, natural AI Curator + Builder voice, "
            "NO hashtags, NO rocket/fire emoji spam, NO URLs in the main tweet(s)."
        )
    )
    card_headline: str = Field(description="Short crisp title for the visual card (<= 65 chars).")
    card_subtitle: str = Field(description="1-line factual subtitle from real data (<= 110 chars).")
    card_bullets: list[str] = Field(
        default_factory=list,
        description="Up to 3 crisp, factual 1-line highlights from the source data (<= 95 chars each).",
    )
    card_takeaway: str = Field(description="1-line grounded builder takeaway (<= 120 chars).")


def load_style_examples(path: Path) -> dict:
    """Load optional feed style examples & voice notes for adaptive style matching."""
    if not path.exists():
        return {"voice_notes": [], "examples": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "voice_notes": data.get("voice_notes") or [],
                "examples": data.get("examples") or [],
            }
    except Exception as exc:
        logger.warning("Failed to load style examples from %s: %s", path, exc)
    return {"voice_notes": [], "examples": []}


def _rank_candidates_for_variety(
    candidates: list[CandidateItem],
    source_penalties: dict[SourceType, int],
    max_per_source: int = 3,
) -> list[CandidateItem]:
    """Select a diverse top-N shortlist across sources to feed into Gemini."""
    grouped: dict[SourceType, list[CandidateItem]] = {s: [] for s in SourceType}
    for c in candidates:
        grouped[c.source_type].append(c)

    for s in grouped:
        grouped[s].sort(key=lambda x: x.popularity_score, reverse=True)

    # Order sources by lowest recent penalty first
    ordered_sources = sorted(SourceType, key=lambda s: source_penalties.get(s, 0))
    shortlist: list[CandidateItem] = []
    for s in ordered_sources:
        shortlist.extend(grouped[s][:max_per_source])
    return shortlist


def _word_truncate(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    trimmed = text[: max_len - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{trimmed}..." if trimmed else text[: max_len - 3] + "..."


def _summary_bullets(summary: str, max_bullets: int = 3) -> list[str]:
    parts = [p.strip(" .") for p in summary.replace(" · ", ". ").split(". ") if p.strip()]
    bullets: list[str] = []
    for part in parts:
        if len(part) < 12:
            continue
        bullets.append(_word_truncate(part, 95))
        if len(bullets) >= max_bullets:
            break
    return bullets


def _deterministic_fallback(
    candidate: CandidateItem,
    forced_format: PostFormat | None = None,
) -> GeneratedPost:
    """Safe zero-hallucination fallback when Gemini is unavailable or not configured."""
    spec_lines = [f"- {s.label}: {s.value}" for s in candidate.specs[:4]]
    bullets = _summary_bullets(candidate.summary)

    if candidate.source_type == SourceType.AI_NEWS:
        publisher = (candidate.raw_metrics or {}).get("publisher") or "AI Update"
        headline = _word_truncate(candidate.title, 115)
        detail = _word_truncate(candidate.summary, 110)
        tweet_1 = f"{headline}\n\n- Source: {publisher}\n- {detail}\n\nHow does this shift your stack?"
    elif candidate.source_type == SourceType.MODEL_BENCHMARK and candidate.comparison_rows:
        top_row = candidate.comparison_rows[0]
        tweet_1 = (
            "Fresh AI model spec check:\n\n"
            + "\n".join(spec_lines[:3])
            + f"\n\nTop row: {top_row[0]} ({' | '.join(top_row[1:4])})"
        )
    else:
        tweet_1 = f"{candidate.title}\n\n" + "\n".join(spec_lines[:3]) + "\n\nWorth watching?"

    fmt = forced_format or PostFormat.SINGLE
    tweets = [tweet_1]
    if fmt == PostFormat.THREAD:
        if candidate.comparison_rows:
            lines = [f"- {r[0]}: {' | '.join(r[1:4])}" for r in candidate.comparison_rows[1:4]]
            if lines:
                tweets.append("More specs from this snapshot:\n\n" + "\n".join(lines))
        elif candidate.source_type == SourceType.AI_NEWS and bullets:
            tweets.append(
                "Key takeaways from the announcement:\n\n"
                + "\n".join(f"- {b}" for b in bullets[:2])
            )
        elif len(candidate.specs) > 3:
            tweet_2 = "Key specs from the live release:\n\n" + "\n".join(
                f"- {s.label}: {s.value}" for s in candidate.specs[2:6]
            )
            tweets.append(tweet_2)

    return GeneratedPost(
        candidate_id=candidate.item_id,
        source_type=candidate.source_type,
        post_format=fmt,
        tweets=tweets,
        reply_source_text=f"Source & full details: {candidate.url}",
        card_headline=_word_truncate(candidate.title, 65),
        card_subtitle=_word_truncate(candidate.summary, 110),
        card_specs=candidate.specs[:6],
        card_bullets=bullets if (candidate.source_type == SourceType.AI_NEWS and len(bullets) >= 2) else [],
        card_takeaway=(
            f"Reported by {(candidate.raw_metrics or {}).get('publisher', 'AI press')} · Live feed update."
            if candidate.source_type == SourceType.AI_NEWS
            else "Real-time metrics pulled directly from public registry APIs."
        ),
        comparison_headers=candidate.comparison_headers,
        comparison_rows=candidate.comparison_rows,
        source_url=candidate.url,
    )


def curate_and_generate_post(
    candidates: list[CandidateItem],
    source_penalties: dict[SourceType, int],
    settings: Settings,
) -> GeneratedPost:
    if not candidates:
        raise ValueError("No unseen candidates available to generate a post.")

    shortlist = _rank_candidates_for_variety(candidates, source_penalties, max_per_source=2)
    candidate_map = {c.item_id: c for c in shortlist}

    forced_format: PostFormat | None = None
    if settings.post_format_override in ("single", "thread"):
        forced_format = PostFormat(settings.post_format_override)

    if not settings.gemini_api_key.strip():
        logger.warning("GEMINI_API_KEY not set; using deterministic template fallback.")
        return _deterministic_fallback(shortlist[0], forced_format=forced_format)

    client = genai.Client(api_key=settings.gemini_api_key.strip())
    style_cfg = load_style_examples(settings.style_examples_path)

    # Prepare strict factual payload for Gemini (compact to stay well within free-tier quotas)
    payload = [
        {
            "item_id": c.item_id,
            "source_type": c.source_type.value,
            "title": c.title,
            "summary": _word_truncate(c.summary, 350),
            "published_or_updated": c.published_or_updated,
            "specs": [{"label": s.label, "value": s.value} for s in c.specs],
            "comparison_headers": c.comparison_headers,
            "comparison_rows": c.comparison_rows,
            "recently_overused_penalty": source_penalties.get(c.source_type, 0),
        }
        for c in shortlist
    ]

    format_instruction = (
        f"You MUST use post_format='{forced_format.value}'."
        if forced_format
        else (
            "Choose 'single' (~70% of the time) for focused news updates, repo/model/paper spotlights, "
            "or 'thread' (2-3 tweets max) when there is a rich multi-model comparison or multi-point announcement."
        )
    )

    voice_notes = "\n".join(f"- {n}" for n in style_cfg.get("voice_notes", []))
    style_examples_json = json.dumps(style_cfg.get("examples", [])[:6], indent=2)

    prompt = f"""You are an AI curator & builder growing an organic X (Twitter) account.
Pick the single highest-signal, most timely AI update or release from the verified CANDIDATES JSON below.
Prefer items with a lower `recently_overused_penalty` and strong breaking-news or builder appeal so the feed stays fresh and varied.

VOICE & FEED STYLE ADAPTATION:
Match the pacing, hook punchiness, bullet formatting, and conversational tone of the STYLE EXAMPLES below — while keeping 100% original writing about the chosen live candidate.
{voice_notes}

STYLE EXAMPLES FROM TARGET FEED:
{style_examples_json}

CRITICAL RULES:
1. ZERO FABRICATION: Only state numbers, specs, prices, parameter counts, star counts, dates, or claims that appear explicitly in the chosen candidate's JSON. Never invent numbers or details.
2. NATURAL CURATOR + BUILDER VOICE: Open with a scroll-stopping hook (no "Just in:", no "BREAKING:"). Organize key points with short scannable lines or bullets. End with a sharp takeaway or genuine question that invites replies.
3. NO SPAM: Zero hashtags (no #AI, no #LLM), zero rocket/fire emoji spam, no "Thread 🧵" cliché, no "Game changer!".
4. CHARACTER LIMIT: Every tweet in `tweets` MUST be <= 260 characters. Do NOT include any URLs in `tweets` (we attach the source link in an auto-reply for reach).
5. {format_instruction}
6. For `card_bullets`, provide 2-3 crisp, factual 1-line highlights (<= 95 chars each) summarizing what changed or why it matters.
7. Mention that visuals/specs are attached naturally if helpful, without sounding robotic.

CANDIDATES JSON:
{json.dumps(payload, indent=2)}
"""

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_CuratedOutput,
                temperature=0.55,
            ),
        )
        parsed = _CuratedOutput.model_validate_json(response.text)
        chosen = candidate_map.get(parsed.selected_item_id) or shortlist[0]
        fmt = forced_format or (
            PostFormat.THREAD if parsed.post_format.strip().lower() == "thread" else PostFormat.SINGLE
        )
        bullets = [b.strip() for b in parsed.card_bullets if b.strip()][:3]
        if not bullets and chosen.source_type == SourceType.AI_NEWS:
            bullets = _summary_bullets(chosen.summary)

        return GeneratedPost(
            candidate_id=chosen.item_id,
            source_type=chosen.source_type,
            post_format=fmt,
            tweets=parsed.tweets,
            reply_source_text=f"Source & full details: {chosen.url}",
            card_headline=_word_truncate(parsed.card_headline, 65),
            card_subtitle=_word_truncate(parsed.card_subtitle, 110),
            card_specs=chosen.specs[:6],
            card_bullets=bullets,
            card_takeaway=_word_truncate(parsed.card_takeaway, 120),
            comparison_headers=chosen.comparison_headers,
            comparison_rows=chosen.comparison_rows,
            source_url=chosen.url,
        )
    except Exception as exc:
        logger.warning("Gemini generation failed (%s); falling back to deterministic template.", exc)
        return _deterministic_fallback(shortlist[0], forced_format=forced_format)
