from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import logging
import re
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from src.models import CandidateItem, SourceType, SpecRow

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "ai-x-automation/0.1 (+https://github.com/KushB13/automation-run)"}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")

AI_KEYWORDS = (
    "ai",
    "llm",
    "model",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "deepmind",
    "xai",
    "grok",
    "llama",
    "meta",
    "mistral",
    "deepseek",
    "qwen",
    "agent",
    "reasoning",
    "inference",
    "gpu",
    "nvidia",
    "hugging face",
    "benchmark",
    "multimodal",
    "open source",
    "open-weight",
    "coding",
    "robotics",
)


@dataclass(frozen=True)
class NewsFeed:
    name: str
    url: str
    category: str
    authority_weight: float
    require_ai_keyword: bool = False


DEFAULT_NEWS_FEEDS: tuple[NewsFeed, ...] = (
    NewsFeed(
        name="OpenAI News",
        url="https://openai.com/news/rss.xml",
        category="Lab Announcement",
        authority_weight=1.55,
    ),
    NewsFeed(
        name="Google AI Blog",
        url="https://blog.google/technology/ai/rss/",
        category="Lab Announcement",
        authority_weight=1.45,
    ),
    NewsFeed(
        name="Hugging Face Blog",
        url="https://huggingface.co/blog/feed.xml",
        category="Open AI Release",
        authority_weight=1.40,
    ),
    NewsFeed(
        name="Simon Willison",
        url="https://simonwillison.net/tags/ai.atom",
        category="AI Engineering",
        authority_weight=1.25,
    ),
    NewsFeed(
        name="TechCrunch AI",
        url="https://techcrunch.com/category/artificial-intelligence/feed/",
        category="AI Industry News",
        authority_weight=1.20,
    ),
    NewsFeed(
        name="VentureBeat AI",
        url="https://venturebeat.com/category/ai/feed/",
        category="AI Industry News",
        authority_weight=1.15,
    ),
    NewsFeed(
        name="MIT Tech Review AI",
        url="https://www.technologyreview.com/topic/artificial-intelligence/feed",
        category="AI Research & Policy",
        authority_weight=1.15,
    ),
    NewsFeed(
        name="Google News AI",
        url=(
            "https://news.google.com/rss/search?"
            "q=(OpenAI+OR+Anthropic+OR+Claude+OR+Gemini+OR+xAI+OR+Grok+OR+DeepSeek+OR+Llama+OR+Mistral)+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
        category="Breaking AI News",
        authority_weight=1.05,
        require_ai_keyword=True,
    ),
)


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    no_tags = TAG_RE.sub(" ", unescaped)
    return WS_RE.sub(" ", no_tags).strip()


def _parse_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _child_text(elem: ET.Element, *names: str) -> str:
    targets = {n.lower() for n in names}
    for child in elem:
        if _local_tag(child.tag) in targets:
            txt = "".join(child.itertext()).strip()
            if txt:
                return txt
    return ""


def _atom_link(elem: ET.Element) -> str:
    fallback = ""
    for child in elem:
        if _local_tag(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "alternate").strip().lower()
        if href and rel == "alternate":
            return href
        if href and not fallback:
            fallback = href
        txt = (child.text or "").strip()
        if txt and not fallback:
            fallback = txt
    return fallback


def _source_publisher(elem: ET.Element, default_name: str) -> str:
    for child in elem:
        if _local_tag(child.tag) == "source":
            txt = "".join(child.itertext()).strip()
            if txt:
                return txt
    return default_name


def _freshness_label(age_hours: float) -> str:
    if age_hours < 1:
        return "< 1h ago"
    if age_hours < 24:
        return f"{int(age_hours)}h ago"
    days = max(1, int(round(age_hours / 24)))
    return f"{days}d ago"


def _title_tokens(title: str) -> set[str]:
    clean = NON_ALNUM_RE.sub(" ", title.lower())
    stop = {"the", "a", "an", "and", "or", "for", "with", "to", "of", "in", "on", "is", "are", "new", "ai"}
    return {tok for tok in clean.split() if len(tok) > 2 and tok not in stop}


def _is_similar_title(t1: str, t2: str) -> bool:
    s1 = _title_tokens(t1)
    s2 = _title_tokens(t2)
    if not s1 or not s2:
        return False
    overlap = len(s1 & s2)
    union = len(s1 | s2)
    return (overlap / union) >= 0.55 or overlap >= min(len(s1), len(s2)) and overlap >= 4


def parse_feed_xml(
    xml_text: str,
    feed: NewsFeed,
    now: datetime | None = None,
    max_age_days: int = 5,
) -> list[CandidateItem]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)

    root = ET.fromstring(xml_text)
    root_name = _local_tag(root.tag)

    entries: list[ET.Element] = []
    if root_name == "rss":
        channel = next((c for c in root if _local_tag(c.tag) == "channel"), None)
        if channel is not None:
            entries = [c for c in channel if _local_tag(c.tag) == "item"]
    elif root_name == "feed":
        entries = [c for c in root if _local_tag(c.tag) == "entry"]
    else:
        entries = [e for e in root.iter() if _local_tag(e.tag) in {"item", "entry"}]

    items: list[CandidateItem] = []
    for entry in entries:
        raw_title = _strip_html(_child_text(entry, "title"))
        if not raw_title:
            continue

        # Google News often appends " - Publisher Name" to headlines
        publisher = _source_publisher(entry, feed.name)
        clean_title = raw_title
        if feed.name == "Google News AI" and " - " in raw_title:
            head, tail = raw_title.rsplit(" - ", 1)
            if len(tail) <= 45 and len(head) >= 20:
                clean_title = head.strip()
                if publisher == feed.name:
                    publisher = tail.strip()

        link = _child_text(entry, "link") or _atom_link(entry)
        if not link.startswith("http"):
            continue

        raw_summary = _child_text(entry, "description", "summary", "content", "encoded")
        summary = _strip_html(raw_summary)
        if len(summary) > 600:
            summary = summary[:597].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
        if not summary:
            summary = f"{clean_title} — reported by {publisher}."

        if feed.require_ai_keyword:
            haystack = f"{clean_title} {summary}".lower()
            if not any(kw in haystack for kw in AI_KEYWORDS):
                continue

        raw_date = _child_text(entry, "pubdate", "published", "updated", "date")
        dt = _parse_datetime(raw_date)
        if dt is not None and dt < cutoff:
            continue
        effective_dt = dt or now
        age_hours = max(0.0, (now - effective_dt).total_seconds() / 3600.0)

        # Recency score: <12h = 1.6x, <24h = 1.35x, <48h = 1.1x, older decays
        if age_hours <= 12:
            recency_mult = 1.60
        elif age_hours <= 24:
            recency_mult = 1.35
        elif age_hours <= 48:
            recency_mult = 1.10
        else:
            recency_mult = max(0.5, 1.0 - (age_hours - 48) / 144.0)

        popularity_score = round(feed.authority_weight * recency_mult * 450.0, 2)
        date_str = effective_dt.strftime("%Y-%m-%d")
        freshness = _freshness_label(age_hours)

        digest = hashlib.sha1(f"{clean_title.lower()}|{link}".encode("utf-8")).hexdigest()[:12]
        domain = urlparse(link).netloc.lower()
        # Google News links are JS redirectors that don't render clean article screenshots
        screenshot_url = "" if "news.google.com" in domain else link

        specs = [
            SpecRow(label="Source", value=publisher[:28], highlight=True),
            SpecRow(label="Category", value=feed.category, highlight=True),
            SpecRow(label="Freshness", value=freshness),
            SpecRow(label="Published", value=date_str),
        ]

        items.append(
            CandidateItem(
                item_id=f"ai_news:{digest}",
                source_type=SourceType.AI_NEWS,
                title=clean_title,
                url=link,
                summary=summary,
                published_or_updated=date_str,
                popularity_score=popularity_score,
                specs=specs,
                raw_metrics={
                    "publisher": publisher,
                    "feed_name": feed.name,
                    "category": feed.category,
                    "published_iso": effective_dt.isoformat(),
                    "age_hours": round(age_hours, 1),
                    "domain": domain,
                },
                screenshot_url=screenshot_url,
            )
        )

    return items


def fetch_ai_news(
    limit: int = 12,
    feeds: tuple[NewsFeed, ...] = DEFAULT_NEWS_FEEDS,
    session: requests.Session | None = None,
    now: datetime | None = None,
    max_age_days: int = 5,
) -> list[CandidateItem]:
    """Fetch breaking AI news and official lab announcements via RSS/Atom feeds."""
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.headers.update(HEADERS)

    all_items: list[CandidateItem] = []
    try:
        for feed in feeds:
            try:
                resp = session.get(feed.url, timeout=15)
                resp.raise_for_status()
                parsed = parse_feed_xml(
                    resp.text,
                    feed=feed,
                    now=now,
                    max_age_days=max_age_days,
                )
                all_items.extend(parsed)
            except Exception as exc:
                logger.warning("AI news feed failed (%s): %s", feed.name, exc)
    finally:
        if own_session:
            session.close()

    # Sort highest-priority & freshest first, then deduplicate overlapping headlines
    all_items.sort(key=lambda x: x.popularity_score, reverse=True)
    deduped: list[CandidateItem] = []
    seen_urls: set[str] = set()
    for item in all_items:
        norm_url = item.url.rstrip("/")
        if norm_url in seen_urls:
            continue
        if any(_is_similar_title(item.title, kept.title) for kept in deduped):
            continue
        seen_urls.add(norm_url)
        deduped.append(item)
        if len(deduped) >= limit:
            break

    return deduped
