from __future__ import annotations

import json
import logging
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src.config import Settings
from src.models import CandidateItem, GeneratedPost, PostFormat, SourceType, SpecRow

logger = logging.getLogger(__name__)


class _CuratedOutput(BaseModel):
    selected_item_id: str = Field(description="Exact item_id from the candidate list.")
    post_format: str = Field(description="Either 'single' or 'thread'.")
    tweets: list[str] = Field(
        description=(
            "1 tweet if post_format=='single', or 2-3 tweets if post_format=='thread'. "
            "Every tweet MUST be <= 265 characters, natural sharp AI builder/analyst voice, "
            "NO hashtags, NO rocket/fire emoji spam, NO URLs in the main tweet(s)."
        )
    )
    card_headline: str = Field(description="Short crisp title for the spec card (<= 65 chars).")
    card_subtitle: str = Field(description="1-line factual subtitle from real data (<= 110 chars).")
    card_takeaway: str = Field(description="1-line grounded builder takeaway (<= 120 chars).")


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


def _deterministic_fallback(
    candidate: CandidateItem,
    forced_format: PostFormat | None = None,
) -> GeneratedPost:
    """Safe zero-hallucination fallback when Gemini is unavailable or not configured."""
    spec_lines = [f"- {s.label}: {s.value}" for s in candidate.specs[:4]]
    if candidate.source_type == SourceType.MODEL_BENCHMARK and candidate.comparison_rows:
        top_row = candidate.comparison_rows[0]
        tweet_1 = (
            f"Fresh AI model spec check:\n\n"
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
        reply_source_text=f"Source & live specs: {candidate.url}",
        card_headline=_word_truncate(candidate.title, 65),
        card_subtitle=_word_truncate(candidate.summary, 110),
        card_specs=candidate.specs[:6],
        card_takeaway="Real-time metrics pulled directly from public registry APIs.",
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

    shortlist = _rank_candidates_for_variety(candidates, source_penalties)
    candidate_map = {c.item_id: c for c in shortlist}

    forced_format: PostFormat | None = None
    if settings.post_format_override in ("single", "thread"):
        forced_format = PostFormat(settings.post_format_override)

    if not settings.gemini_api_key.strip():
        logger.warning("GEMINI_API_KEY not set; using deterministic template fallback.")
        return _deterministic_fallback(shortlist[0], forced_format=forced_format)

    client = genai.Client(api_key=settings.gemini_api_key.strip())

    # Prepare strict factual payload for Gemini
    payload = [
        {
            "item_id": c.item_id,
            "source_type": c.source_type.value,
            "title": c.title,
            "summary": c.summary,
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
            "Choose 'single' (~70% of the time) for focused repo/model/paper spotlights, "
            "or 'thread' (2-3 tweets max) when there is a rich multi-model comparison or deep spec breakdown."
        )
    )

    prompt = f"""You are an AI engineer & tech analyst growing an organic X (Twitter) account.
Pick the single most interesting, high-signal AI candidate from the verified JSON list below.
Prefer items with a lower `recently_overused_penalty` so the feed stays varied.

CRITICAL RULES:
1. ZERO FABRICATION: Only state numbers, specs, prices, parameter counts, star counts, or benchmarks that appear explicitly in the chosen candidate's JSON. Never invent numbers.
2. NATURAL BUILDER VOICE: Write like a sharp human AI builder sharing a real find. Start with a crisp, curiosity-driven hook. Organize specs cleanly with short lines or bullets. End with a sharp takeaway or genuine question for replies.
3. NO SPAM: Zero hashtags (no #AI, no #LLM), zero rocket/fire emoji spam, no "Thread 🧵" cliché, no "Game changer!".
4. CHARACTER LIMIT: Every tweet in `tweets` MUST be <= 260 characters. Do NOT include any URLs in `tweets` (we attach the source link in an auto-reply for reach).
5. {format_instruction}
6. Mention that screenshots/spec breakdown are attached naturally if helpful, without sounding robotic.

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
                temperature=0.5,
            ),
        )
        parsed = _CuratedOutput.model_validate_json(response.text)
        chosen = candidate_map.get(parsed.selected_item_id) or shortlist[0]
        fmt = forced_format or (
            PostFormat.THREAD if parsed.post_format.strip().lower() == "thread" else PostFormat.SINGLE
        )
        return GeneratedPost(
            candidate_id=chosen.item_id,
            source_type=chosen.source_type,
            post_format=fmt,
            tweets=parsed.tweets,
            reply_source_text=f"Source & full live specs: {chosen.url}",
            card_headline=parsed.card_headline,
            card_subtitle=parsed.card_subtitle,
            card_specs=chosen.specs[:6],
            card_takeaway=parsed.card_takeaway,
            comparison_headers=chosen.comparison_headers,
            comparison_rows=chosen.comparison_rows,
            source_url=chosen.url,
        )
    except Exception as exc:
        logger.warning("Gemini generation failed (%s); falling back to deterministic template.", exc)
        return _deterministic_fallback(shortlist[0], forced_format=forced_format)
