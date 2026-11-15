from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from jinja2 import Template
from playwright.sync_api import sync_playwright

from src.models import GeneratedPost, SourceType

SOURCE_LABELS: dict[SourceType, tuple[str, str]] = {
    SourceType.AI_NEWS: ("AI NEWS · BREAKING UPDATE", "#818cf8"),
    SourceType.HUGGINGFACE_MODEL: ("HUGGING FACE · TRENDING MODEL", "#f59e0b"),
    SourceType.HUGGINGFACE_PAPER: ("HUGGING FACE · DAILY PAPER", "#ec4899"),
    SourceType.GITHUB_REPO: ("GITHUB · TRENDING AI REPO", "#22d3ee"),
    SourceType.MODEL_BENCHMARK: ("LIVE MODEL SPECS & PRICING", "#10b981"),
}

CARD_TEMPLATE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #070a10;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    color: #e6edf3;
    padding: 0;
  }
  .card {
    width: 1120px;
    background: linear-gradient(155deg, #0d131f 0%, #090d16 100%);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 22px;
    padding: 40px 44px 34px;
    position: relative;
    overflow: hidden;
  }
  .accent-top {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: {{ accent }};
  }
  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.09em;
    color: {{ accent }};
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.09);
    padding: 6px 14px;
    border-radius: 999px;
  }
  .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: {{ accent }};
  }
  .date-tag {
    font-size: 13px;
    color: #8b949e;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  h1 {
    font-size: 34px;
    line-height: 1.2;
    font-weight: 750;
    color: #f8fafc;
    letter-spacing: -0.02em;
    margin-bottom: 10px;
    word-break: break-word;
  }
  .subtitle {
    font-size: 18px;
    line-height: 1.45;
    color: #94a3b8;
    margin-bottom: 26px;
  }
  .bullets-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 22px;
  }
  .bullet-item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    background: rgba(15, 23, 42, 0.72);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 12px;
    padding: 14px 18px;
    font-size: 17px;
    line-height: 1.4;
    color: #e2e8f0;
  }
  .bullet-num {
    flex: 0 0 auto;
    width: 24px;
    height: 24px;
    border-radius: 6px;
    background: {{ accent }}22;
    border: 1px solid {{ accent }}66;
    color: {{ accent }};
    font-size: 13px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    margin-top: 1px;
  }
  .specs-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin-bottom: 24px;
  }
  .spec-box {
    background: rgba(15, 23, 42, 0.72);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 14px;
    padding: 16px 18px;
  }
  .spec-box.highlight {
    border-color: {{ accent }}55;
    background: rgba(15, 23, 42, 0.92);
  }
  .spec-label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #8b949e;
    margin-bottom: 6px;
  }
  .spec-value {
    font-size: 21px;
    font-weight: 700;
    color: #f1f5f9;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    word-break: break-word;
  }
  .spec-box.highlight .spec-value {
    color: {{ accent }};
  }
  .table-wrap {
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 24px;
    background: rgba(15, 23, 42, 0.65);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 15px;
  }
  th {
    text-align: left;
    padding: 13px 16px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #94a3b8;
    background: rgba(30, 41, 59, 0.65);
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  }
  td {
    padding: 13px 16px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.1);
    color: #e2e8f0;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  td:first-child {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
    font-weight: 650;
    color: #f8fafc;
  }
  tr:last-child td { border-bottom: none; }
  .takeaway {
    background: rgba(30, 41, 59, 0.45);
    border-left: 3px solid {{ accent }};
    border-radius: 8px;
    padding: 14px 18px;
    font-size: 16px;
    line-height: 1.45;
    color: #cbd5e1;
    margin-bottom: 22px;
  }
  .footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 16px;
    border-top: 1px solid rgba(148, 163, 184, 0.12);
    font-size: 13px;
    color: #64748b;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .handle {
    color: #94a3b8;
    font-weight: 600;
  }
</style>
</head>
<body>
  <div class="card">
    <div class="accent-top"></div>
    <div class="header-row">
      <div class="badge"><span class="dot"></span>{{ badge_label }}</div>
      <div class="date-tag">LIVE DATA · {{ date_str }}</div>
    </div>
    <h1>{{ headline }}</h1>
    <div class="subtitle">{{ subtitle }}</div>

    {% if comparison_headers and comparison_rows %}
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            {% for h in comparison_headers %}
            <th>{{ h }}</th>
            {% endfor %}
          </tr>
        </thead>
        <tbody>
          {% for row in comparison_rows %}
          <tr>
            {% for cell in row %}
            <td>{{ cell }}</td>
            {% endfor %}
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% elif bullets %}
    <div class="bullets-list">
      {% for b in bullets %}
      <div class="bullet-item">
        <span class="bullet-num">0{{ loop.index }}</span>
        <span>{{ b }}</span>
      </div>
      {% endfor %}
    </div>
    {% if specs %}
    <div class="specs-grid">
      {% for s in specs[:3] %}
      <div class="spec-box {% if s.highlight %}highlight{% endif %}">
        <div class="spec-label">{{ s.label }}</div>
        <div class="spec-value">{{ s.value }}</div>
      </div>
      {% endfor %}
    </div>
    {% endif %}
    {% elif specs %}
    <div class="specs-grid">
      {% for s in specs %}
      <div class="spec-box {% if s.highlight %}highlight{% endif %}">
        <div class="spec-label">{{ s.label }}</div>
        <div class="spec-value">{{ s.value }}</div>
      </div>
      {% endfor %}
    </div>
    {% endif %}

    {% if takeaway %}
    <div class="takeaway">{{ takeaway }}</div>
    {% endif %}

    <div class="footer">
      <span>Verified Source: {{ source_domain }}</span>
      {% if handle %}<span class="handle">@{{ handle }}</span>{% endif %}
    </div>
  </div>
</body>
</html>
"""
)


def render_spec_card(
    post: GeneratedPost,
    output_path: Path,
    x_handle: str = "",
) -> Path:
    """Render a crisp dark-mode real-data spec/news card PNG via headless Chromium."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    badge_label, accent = SOURCE_LABELS.get(
        post.source_type, ("AI REAL-DATA SNAPSHOT", "#22d3ee")
    )
    domain = urlparse(post.source_url).netloc or "public-api"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d UTC")
    clean_handle = x_handle.strip().lstrip("@")

    html = CARD_TEMPLATE.render(
        badge_label=badge_label,
        accent=accent,
        date_str=date_str,
        headline=post.card_headline,
        subtitle=post.card_subtitle,
        specs=post.card_specs[:6],
        bullets=post.card_bullets[:3],
        comparison_headers=post.comparison_headers,
        comparison_rows=post.comparison_rows[:6],
        takeaway=post.card_takeaway,
        source_domain=domain,
        handle=clean_handle,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900}, device_scale_factor=2)
        page.set_content(html, wait_until="load")
        page.locator(".card").screenshot(path=str(output_path))
        browser.close()

    return output_path
