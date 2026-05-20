"""NMG Wonen Eindhoven: Playwright listing crawl + HTTP detail pages."""

from __future__ import annotations

import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from src.filters import INACTIVE_LISTING_MARKERS
from src.models import Listing
from src.web_fetch import HEADERS

LIST_URL = "https://nmgwonen.nl/huurwoningen/eindhoven/"
DETAIL_RE = re.compile(r"/woning/[^/]+/?$", re.I)


def _outdoor(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras"))


def _extract_int(text: str) -> int | None:
    match = re.search(r"(\d[\d\.,]*)", text or "")
    if not match:
        return None
    normalized = re.sub(r"[^\d]", "", match.group(1))
    return int(normalized) if normalized else None


def _collect_detail_urls(list_url: str, max_pages: int) -> list[str]:
    storage = os.getenv("PLAYWRIGHT_STORAGE_STATE_PATH", "data/playwright_state.json")
    seen: set[str] = set()
    ordered: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="nl-NL")
        if os.path.exists(storage):
            context.close()
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"], locale="nl-NL", storage_state=storage
            )
        page = context.new_page()
        for page_num in range(1, max_pages + 1):
            url = list_url if page_num == 1 else f"{list_url.rstrip('/')}/page/{page_num}/"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                break
            page.wait_for_timeout(2500)
            for _ in range(12):
                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(800)
            hrefs = page.locator("a[href*='/woning/']").evaluate_all(
                "els => els.map(e => e.getAttribute('href'))"
            )
            new_count = 0
            for href in hrefs:
                if not href:
                    continue
                path = urlparse(href).path
                if not DETAIL_RE.search(path):
                    continue
                full = urljoin("https://nmgwonen.nl", href).split("?")[0].rstrip("/") + "/"
                if full in seen:
                    continue
                seen.add(full)
                ordered.append(full)
                new_count += 1
            if new_count == 0 and page_num > 1:
                break
        context.close()
        browser.close()
    return ordered


def _parse_detail(url: str) -> Listing | None:
    r = requests.get(url, headers=HEADERS, timeout=25)
    if r.status_code >= 400:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    lowered = text.lower()
    if any(m in lowered for m in INACTIVE_LISTING_MARKERS):
        return None
    if "eindhoven" not in lowered and "eindhoven" not in url.lower():
        return None

    h1 = soup.select_one("h1")
    title = h1.get_text(" ", strip=True) if h1 else url.rstrip("/").split("/")[-1]
    amounts = []
    for m in re.finditer(r"€\s*([\d\.\s]{2,10})", text):
        raw = m.group(1).replace(".", "").replace(" ", "")
        if raw.isdigit():
            val = int(raw)
            if 200 <= val <= 6000:
                amounts.append(val)
    rent = min(amounts) if amounts else None
    size_m = re.search(r"(\d{2,3})\s*m\s*²", text, re.I) or re.search(r"(\d{2,3})\s*m2\b", text, re.I)
    size = int(size_m.group(1)) if size_m else None
    pc = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", text)
    location = title
    if pc:
        location = f"{title}, {pc.group(1)} {pc.group(2).upper()}, Eindhoven"

    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return Listing(
        source="nmg",
        source_id=f"nmg-{slug}",
        title=title,
        url=url,
        location=location,
        rent_eur=rent,
        size_m2=size,
        outdoor_space=_outdoor(text),
        contract_months=None,
        available_from=None,
        notes=None,
    )


def fetch_nmg_eindhoven_listings(list_url: str | None = None) -> list[Listing]:
    base = list_url or os.getenv("NMG_LIST_URL", LIST_URL)
    max_pages = int(os.getenv("NMG_MAX_PAGES", "15"))
    max_details = int(os.getenv("NMG_MAX_DETAIL_PAGES", "80"))
    urls = _collect_detail_urls(base, max_pages)[:max_details]

    listings: list[Listing] = []
    seen: set[str] = set()
    interval = float(os.getenv("NMG_DETAIL_INTERVAL", "0.3"))
    for url in urls:
        try:
            listing = _parse_detail(url)
        except Exception:
            continue
        if not listing or listing.source_id in seen:
            continue
        if listing.rent_eur is None or listing.size_m2 is None:
            continue
        seen.add(listing.source_id)
        listings.append(listing)
        time.sleep(interval)
    return listings
