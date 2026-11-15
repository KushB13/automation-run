from __future__ import annotations

import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


BLOCKED_PAGE_PHRASES = (
    "just a moment...",
    "verify you are human",
    "checking your browser",
    "enable javascript and cookies",
    "access denied",
    "subscribe to continue reading",
    "please turn on javascript",
    "attention required! | cloudflare",
)


def is_blocked_or_cluttered(status_code: int | None, body_text: str) -> bool:
    """Return True if a webpage failed, hit an anti-bot/paywall gate, or has almost no text."""
    if status_code is not None and status_code >= 400:
        return True
    cleaned = " ".join((body_text or "").lower().split())
    if len(cleaned) < 150:
        return True
    return any(phrase in cleaned for phrase in BLOCKED_PAGE_PHRASES)


def capture_live_webpage(
    url: str,
    output_path: Path,
    timeout_ms: int = 25_000,
) -> Path | None:
    """Capture a crisp dark-mode screenshot of the actual live source webpage, skipping blocked/cluttered pages."""
    if not url:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                device_scale_factor=2,
                color_scheme="dark",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status_code = response.status if response else None
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                # Some pages keep background polling open; domcontentloaded + brief settle is enough
                page.wait_for_timeout(1_500)

            # Best-effort hide intrusive cookie/consent banners so real page content stays clean
            page.add_style_tag(
                content="""
                [id*="cookie" i], [class*="cookie" i], [aria-label*="cookie" i],
                [id*="consent" i], [class*="consent" i], [id*="onetrust" i],
                [class*="onetrust" i], [class*="paywall" i] {
                    display: none !important;
                }
                """
            )
            body_text = page.inner_text("body")
            if is_blocked_or_cluttered(status_code, body_text):
                logger.info("Skipping live screenshot for %s (blocked/paywalled/thin page).", url)
                browser.close()
                return None

            page.screenshot(path=str(output_path), full_page=False)
            browser.close()

        if output_path.exists() and output_path.stat().st_size > 10_000:
            return output_path
        return None
    except Exception as exc:
        logger.warning("Live webpage screenshot failed for %s: %s", url, exc)
        return None
