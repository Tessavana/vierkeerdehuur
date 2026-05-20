"""Funda huur Eindhoven: search ItemList JSON-LD + detail pages for rent/size/address."""

from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.filters import INACTIVE_LISTING_MARKERS
from src.filters import detect_outdoor
from src.listing_detail import parse_detail_html
from src.models import Listing
from playwright.sync_api import sync_playwright

from src.web_fetch import HEADERS, fetch_html_with_fallback

_SEARCH_BASE = "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D"
_DETAIL_SKIP = ("/parkeergelegenheid-", "/garage-", "/opslag-")


def _extract_int(text: str) -> int | None:
    match = re.search(r"(\d[\d\.,]*)", text or "")
    if not match:
        return None
    normalized = re.sub(r"[^\d]", "", match.group(1))
    return int(normalized) if normalized else None


def _search_urls(max_pages: int) -> list[str]:
    urls = [_SEARCH_BASE]
    for page in range(2, max_pages + 1):
        urls.append(f"{_SEARCH_BASE}&search_result={page - 1}")
    return urls


def _urls_from_search_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for item in data.get("itemListElement") or []:
            if not isinstance(item, dict):
                continue
            u = str(item.get("url", "")).strip()
            if u and "/detail/huur/eindhoven/" in u:
                found.append(u.split("?")[0])
    if found:
        return found
    for a in soup.select('a[href*="/detail/huur/eindhoven/"]'):
        href = a.get("href", "")
        if not href:
            continue
        full = urljoin("https://www.funda.nl", href)
        if any(skip in full for skip in _DETAIL_SKIP):
            continue
        found.append(full.split("?")[0])
    return found


def _accept_cookies(page) -> None:
    for sel in (
        "button#onetrust-accept-btn-handler",
        "button:has-text('Accepteren')",
        "button:has-text('Alles accepteren')",
    ):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click(timeout=4000)
                return
        except Exception:
            continue


def _collect_search_urls_playwright(max_pages: int) -> list[str]:
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

        for search_url in _search_urls(max_pages):
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=120000)
                _accept_cookies(page)
                page.wait_for_timeout(4000)
                try:
                    page.wait_for_selector('a[href*="/detail/huur/eindhoven/"]', timeout=60000)
                except Exception:
                    pass
                for _ in range(10):
                    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                    page.wait_for_timeout(600)
                hrefs = page.locator('a[href*="/detail/huur/eindhoven/"]').evaluate_all(
                    "els => els.map(e => e.href)"
                )
                page_urls = []
                for href in hrefs:
                    if not href or any(skip in href for skip in _DETAIL_SKIP):
                        continue
                    page_urls.append(href.split("?")[0])
                if not page_urls:
                    page_urls = _urls_from_search_html(page.content())
            except Exception:
                page_urls = []

            new_on_page = 0
            for u in page_urls:
                if u in seen:
                    continue
                seen.add(u)
                ordered.append(u)
                new_on_page += 1
            if not page_urls or new_on_page == 0:
                break
            time.sleep(float(os.getenv("FUNDA_SEARCH_INTERVAL", "0.35")))

        context.close()
        browser.close()
    return ordered


def _fetch_funda_api_listings(max_results: int) -> list[Listing]:
    """Use Funda's app API (via pyfunda) when HTML/Playwright is blocked."""
    if os.getenv("FUNDA_USE_API", "true").strip().lower() in {"0", "false", "no", "off"}:
        return []
    try:
        from funda import Funda
    except ImportError:
        return []

    max_price = int(os.getenv("FUNDA_API_MAX_PRICE", "2500"))
    listings: list[Listing] = []
    seen: set[str] = set()

    with Funda() as client:
        for item in client.search("eindhoven", category="rent", max_price=max_price):
            if len(listings) >= max_results:
                break
            url = (item.url or "").split("?")[0]
            if not url or url in seen:
                continue
            rent = item.price.amount if item.price else None
            size = item.living_area
            if rent is None or size is None:
                continue
            seen.add(url)
            addr = item.address
            parts = []
            if addr:
                street = " ".join(
                    p
                    for p in (addr.street_name, addr.house_number, addr.house_number_suffix)
                    if p
                ).strip()
                if street:
                    parts.append(street)
                if addr.postcode:
                    parts.append(addr.postcode)
                if addr.city:
                    parts.append(addr.city)
            location = ", ".join(parts) or "Eindhoven"
            desc = (item.description or "")[:4000]
            outdoor_known, outdoor_space = detect_outdoor(desc)
            listed = None
            if item.publication_date:
                listed = str(item.publication_date)[:10]
            listings.append(
                Listing(
                    source="funda",
                    source_id=str(item.global_id or item.tiny_id or url.rstrip("/").split("/")[-1]),
                    title=item.title or "Funda listing",
                    url=url,
                    location=location,
                    rent_eur=int(rent),
                    size_m2=int(size),
                    outdoor_space=outdoor_space,
                    outdoor_known=outdoor_known,
                    contract_months=None,
                    available_from=None,
                    notes=desc or None,
                    platform_listed_date=listed,
                )
            )
    return listings


def _collect_search_urls(max_pages: int) -> list[str]:
    urls = _collect_search_urls_playwright(max_pages)
    if urls:
        return urls
    seen: set[str] = set()
    ordered: list[str] = []
    for search_url in _search_urls(max_pages):
        try:
            fetched = fetch_html_with_fallback(search_url)
            page_urls = _urls_from_search_html(fetched.html)
        except Exception:
            continue
        new_on_page = 0
        for u in page_urls:
            if u in seen:
                continue
            seen.add(u)
            ordered.append(u)
            new_on_page += 1
        if not page_urls or new_on_page == 0:
            break
    return ordered


def _parse_detail(html: str, url: str) -> Listing | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    lowered = text.lower()
    if any(m in lowered for m in INACTIVE_LISTING_MARKERS):
        return None

    fields = parse_detail_html(html, url)
    name = "Funda listing"
    rent: int | None = None
    size: int | None = None
    street = ""
    locality = "Eindhoven"
    postcode = ""

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        objs = data if isinstance(data, list) else [data]
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") == "Product" or "Product" in (obj.get("@type") or []):
                name = str(obj.get("name", name))
                offers = obj.get("offers") if isinstance(obj.get("offers"), dict) else {}
                rent = _extract_int(str(offers.get("price", ""))) or rent
                addr = obj.get("address") if isinstance(obj.get("address"), dict) else {}
                street = str(addr.get("streetAddress", street))
                locality = str(addr.get("addressLocality", locality))
            if obj.get("@type") in ("Apartment", "House", "Residence", "SingleFamilyResidence"):
                name = str(obj.get("name", name))
                addr = obj.get("address") if isinstance(obj.get("address"), dict) else {}
                street = str(addr.get("streetAddress", street))
                locality = str(addr.get("addressLocality", locality))

    if rent is None:
        rent = _extract_int(text)
    if size is None:
        m = re.search(r"(\d{2,3})\s*m\s*²", text, re.I) or re.search(r"(\d{2,3})\s*m2\b", text, re.I)
        size = int(m.group(1)) if m else None
    m_pc = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", text)
    if m_pc:
        postcode = f"{m_pc.group(1)} {m_pc.group(2).upper()}"

    location = ", ".join(p for p in (street, postcode, locality) if p) or "Eindhoven"
    source_id = url.rstrip("/").split("/")[-1]
    desc = fields.get("description") or ""
    outdoor_known, outdoor_space = detect_outdoor(f"{desc} {text}")
    return Listing(
        source="funda",
        source_id=source_id,
        title=name,
        url=url,
        location=location,
        rent_eur=rent,
        size_m2=size,
        outdoor_space=outdoor_space,
        outdoor_known=outdoor_known,
        contract_months=None,
        available_from=fields.get("available_from"),
        notes=desc[:4000] or None,
        platform_listed_date=fields.get("platform_listed_date"),
    )


def fetch_funda_eindhoven_huur_listings(search_url: str | None = None) -> list[Listing]:
    max_details = int(os.getenv("FUNDA_MAX_DETAIL_PAGES", "120"))
    api_listings = _fetch_funda_api_listings(max_details)
    if api_listings:
        return api_listings

    max_pages = int(os.getenv("FUNDA_MAX_PAGES", "25"))
    detail_urls = _collect_search_urls(max_pages)[:max_details]

    listings: list[Listing] = []
    seen_ids: set[str] = set()
    interval = float(os.getenv("FUNDA_DETAIL_INTERVAL", "0.45"))

    for url in detail_urls:
        try:
            fetched = fetch_html_with_fallback(url)
            listing = _parse_detail(fetched.html, url)
        except Exception:
            continue
        if not listing or listing.source_id in seen_ids:
            continue
        if listing.rent_eur is None or listing.size_m2 is None:
            continue
        seen_ids.add(listing.source_id)
        listings.append(listing)
        time.sleep(interval)

    return listings
