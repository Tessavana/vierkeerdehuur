import os
from dataclasses import dataclass

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
}


@dataclass(frozen=True)
class FetchResult:
    html: str
    final_url: str
    used_browser: bool


def fetch_html_with_fallback(url: str, timeout: int = 25) -> FetchResult:
    response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    if response.status_code < 400 and not _looks_like_antibot(response.text):
        return FetchResult(html=response.text, final_url=str(response.url), used_browser=False)

    if not _env_flag("ENABLE_PLAYWRIGHT_FALLBACK", default=True):
        response.raise_for_status()
        return FetchResult(html=response.text, final_url=str(response.url), used_browser=False)

    html, final_url = _fetch_with_playwright(url)
    return FetchResult(html=html, final_url=final_url, used_browser=True)


def fetch_html_with_playwright(url: str, wait_ms: int = 5000) -> FetchResult:
    """Always render with Chromium (for heavy client-side listing pages)."""
    html, final_url = _fetch_with_playwright(url, wait_ms=wait_ms)
    return FetchResult(html=html, final_url=final_url, used_browser=True)


def _looks_like_antibot(html: str) -> bool:
    text = html[:1600].lower()
    hints = ("just a moment", "cloudflare", "captcha", "access denied", "je bent bijna", "bot")
    return any(h in text for h in hints)


def _fetch_with_playwright(url: str, wait_ms: int = 3000) -> tuple[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright fallback requested but not installed. "
            "Run: pip install playwright && python -m playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="nl-NL")
        storage_state_path = os.getenv("PLAYWRIGHT_STORAGE_STATE_PATH", "data/playwright_state.json")
        if os.path.exists(storage_state_path):
            context.close()
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"], locale="nl-NL", storage_state=storage_state_path
            )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(int(wait_ms))
        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
    return html, final_url


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
