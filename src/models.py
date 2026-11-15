from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    HUGGINGFACE_MODEL = "huggingface_models"
    HUGGINGFACE_PAPER = "huggingface_papers"
    GITHUB_REPO = "github_trending"
    MODEL_BENCHMARK = "model_benchmarks"


class PostFormat(str, Enum):
    SINGLE = "single"
    THREAD = "thread"


class SpecRow(BaseModel):
    label: str
    value: str
    highlight: bool = False


class CandidateItem(BaseModel):
    item_id: str
    source_type: SourceType
    title: str
    url: str
    summary: str
    published_or_updated: str = ""
    popularity_score: float = 0.0
    specs: list[SpecRow] = Field(default_factory=list)
    comparison_headers: list[str] = Field(default_factory=list)
    comparison_rows: list[list[str]] = Field(default_factory=list)
    raw_metrics: dict[str, Any] = Field(default_factory=dict)
    screenshot_url: str = ""
    screenshot_selector: str | None = None


class GeneratedPost(BaseModel):
    candidate_id: str
    source_type: SourceType
    post_format: PostFormat
    tweets: list[str]
    reply_source_text: str
    card_headline: str
    card_subtitle: str
    card_specs: list[SpecRow] = Field(default_factory=list)
    card_takeaway: str = ""
    comparison_headers: list[str] = Field(default_factory=list)
    comparison_rows: list[list[str]] = Field(default_factory=list)
    source_url: str


class HistoryEntry(BaseModel):
    item_id: str
    source_type: SourceType
    title: str
    url: str
    post_format: PostFormat
    tweets: list[str]
    tweet_ids: list[str] = Field(default_factory=list)
    posted_at: str
    dry_run: bool = False
