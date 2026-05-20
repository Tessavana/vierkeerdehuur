"""Pararius Eindhoven: Playwright search + detail enrichment per listing."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from src.filters import detect_outdoor
from src.listing_detail import parse_detail_html
from src.models import Listing
from src.web_fetch import HEADERS, fetch_html_with_fallback

_LIST_URL = "https://www.pararius.com/apartments/eindhoven"


def _extract_int(text: str) -> int | None:
    match = re.search(r"(\d[\d\.,]*)", text or "")
    if not match:
        return None
    normalized = re.sub(r"[^\d]", "", match.group(1))
    return int(normalized) if normalized else None


def _card_is_new_today(card) -> bool:
    blob = card.get_text(" ", strip=True).lower()
    return "vandaag" in blob or "today" in blob


def _collect_card_urls_playwright(list_url: str) -> list[tuple[str, bool]]:
    storage = os.getenv("PLAYWRIGHT_STORAGE_STATE_PATH", "data/playwright_state.json")
    out: list[tuple[str, bool]] = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="nl-NL")
        if os.path.exists(storage):
            context.close()
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"], locale="nl-NL", storage_state=storage
            )
        page = context.new_page()
        page.goto(list_url, wait_until="domcontentloaded", timeout=90000)
        for sel in ("button#onetrust-accept-btn-handler", "button:has-text('Accepteren')"):
            try:
                if page.locator(sel).count():
                    page.locator(sel).first.click(timeout=3000)
                    break
            except Exception:
                pass
        page.wait_for_timeout(3000)
        try:
            page.wait_for_selector("section.listing-search-item", timeout=45000)
        except Exception:
            pass
        for _ in range(8):
            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            page.wait_for_timeout(600)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select("section.listing-search-item"):
            link = card.select_one("a.listing-search-item__link--title")
            if not link or not link.get("href"):
                continue
            href = link["href"]
            if not href.startswith("http"):
                href = "https://www.pararius.com" + href
            key = href.split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            out.append((key, _card_is_new_today(card)))
        context.close()
        browser.close()
    return out


def _parse_card_html(html: str, list_url: str) -> list[tuple[str, bool]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, bool]] = []
    for card in soup.select("section.listing-search-item"):
        link = card.select_one("a.listing-search-item__link--title")
        if not link or not link.get("href"):
            continue
        href = link["href"]
        if not href.startswith("http"):
            href = "https://www.pararius.com" + href
        out.append((href.split("?")[0], _card_is_new_today(card)))
    return out


def fetch_pararius_eindhoven_listings(list_url: str | None = None) -> list[Listing]:
    base = list_url or _LIST_URL
    max_details = int(os.getenv("PARARIUS_MAX_DETAILS", "60"))
    interval = float(os.getenv("PARARIUS_DETAIL_INTERVAL", "0.35"))

    cards = _collect_card_urls_playwright(base)
    if not cards:
        try:
            fetched = fetch_html_with_fallback(base)
            cards = _parse_card_html(fetched.html, base)
        except Exception:
            cards = []

    listings: list[Listing] = []
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date().isoformat()

    for url, card_new in cards[:max_details]:
        try:
            fetched = fetch_html_with_fallback(url)
            fields = parse_detail_html(fetched.html, url)
            soup = BeautifulSoup(fetched.html, "html.parser")
            title_el = soup.select_one("h1") or soup.select_one("a.listing-search-item__link--title")
            title = title_el.get_text(" ", strip=True) if title_el else "Pararius listing"
            loc_el = soup.select_one("div.listing-detail-summary__location") or soup.select_one(
                "div.listing-search-item__location"
            )
            location = loc_el.get_text(" ", strip=True) if loc_el else "Eindhoven"
            text = soup.get_text(" ", strip=True)
            rent_m = re.search(r"€\s*([\d\.\s]+)", text)
            rent = _extract_int(rent_m.group(1)) if rent_m else None
            size_m = re.search(r"(\d{2,3})\s*m\s*²", text, re.I)
            size = int(size_m.group(1)) if size_m else None
            listed = fields.get("platform_listed_date")
            if card_new and not listed:
                listed = today
            desc = fields.get("description") or ""
            outdoor_known, outdoor_space = detect_outdoor(f"{desc} {text}")
            listings.append(
                Listing(
                    source="pararius",
                    source_id=url.rstrip("/").split("/")[-1],
                    title=title,
                    url=url,
                    location=location if "eindhoven" in location.lower() else f"{location}, Eindhoven",
                    rent_eur=rent,
                    size_m2=size,
                    outdoor_space=outdoor_space,
                    outdoor_known=outdoor_known,
                    contract_months=None,
                    available_from=fields.get("available_from"),
                    notes=desc[:4000] or None,
                    platform_listed_date=listed,
                )
            )
        except Exception:
            continue
        time.sleep(interval)
    return listings
