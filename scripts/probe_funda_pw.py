import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from src.web_fetch import HEADERS

url = "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D"
storage = os.getenv("PLAYWRIGHT_STORAGE_STATE_PATH", "data/playwright_state.json")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="nl-NL")
    if os.path.exists(storage):
        context.close()
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"], locale="nl-NL", storage_state=storage
        )
    page = context.new_page()
    page.goto(url, wait_until="networkidle", timeout=120000)
    page.wait_for_timeout(5000)
    html = page.content()
    ids = re.findall(r"/detail/huur/eindhoven/[^\"']+/(\d+)/", html)
    print("ids", len(set(ids)), list(set(ids))[:5])
    hrefs = page.locator('a[href*="/detail/huur/eindhoven/"]').count()
    print("locator count", hrefs)
    context.close()
    browser.close()
