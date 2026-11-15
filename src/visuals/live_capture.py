from __future__ import annotations

import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def capture_live_webpage(
    url: str,
    output_path: Path,
    timeout_ms: int = 25_000,
) -> Path | None:
    """Capture a crisp dark-mode screenshot of the actual live source webpage."""
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
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                # Some pages keep background polling open; domcontentloaded + brief settle is enough
                page.wait_for_timeout(1_500)

            # Best-effort hide intrusive cookie banners so the real page content is clean
            page.add_style_tag(
                content="""
                [id*="cookie"], [class*="cookie"], [aria-label*="cookie" i] {
                    display: none !important;
                }
                """
            )
            page.screenshot(path=str(output_path), full_page=False)
            browser.close()

        if output_path.exists() and output_path.stat().st_size > 10_000:
            return output_path
        return None
    except Exception as exc:
        logger.warning("Live webpage screenshot failed for %s: %s", url, exc)
        return None
