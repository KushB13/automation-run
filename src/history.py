from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from src.models import CandidateItem, HistoryEntry, SourceType


def load_history(path: Path) -> list[HistoryEntry]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    return [HistoryEntry.model_validate(item) for item in data]


def save_history(path: Path, entries: list[HistoryEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep most recent 500 entries to keep git history compact
    trimmed = entries[-500:]
    payload = [entry.model_dump(mode="json") for entry in trimmed]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def filter_unseen_candidates(
    candidates: list[CandidateItem],
    history: list[HistoryEntry],
    cooldown_days: int = 30,
) -> list[CandidateItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
    recent_ids: set[str] = set()
    recent_urls: set[str] = set()

    for entry in history:
        if entry.dry_run:
            continue
        try:
            ts = datetime.fromisoformat(entry.posted_at.replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(timezone.utc)
        if ts >= cutoff:
            recent_ids.add(entry.item_id)
            recent_urls.add(entry.url.rstrip("/"))

    return [
        c for c in candidates
        if c.item_id not in recent_ids and c.url.rstrip("/") not in recent_urls
    ]


def recent_source_penalties(history: list[HistoryEntry], lookback: int = 4) -> dict[SourceType, int]:
    """Count recent source types so the bot rotates naturally across topics."""
    counts: dict[SourceType, int] = {s: 0 for s in SourceType}
    real_entries = [e for e in history if not e.dry_run][-lookback:]
    for idx, entry in enumerate(reversed(real_entries)):
        # Most recent post gets higher weight so we don't repeat the same category back-to-back
        weight = lookback - idx
        counts[entry.source_type] = counts.get(entry.source_type, 0) + weight
    return counts
