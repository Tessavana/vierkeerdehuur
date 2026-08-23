"""Direct Wonen Eindhoven — list tiles via browser HTML, structured fields from cards."""

from __future__ import annotations

import os
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.extract import extract_rent_eur, extract_size_m2
from src.models import Listing
from src.web_fetch import fetch_html_with_fallback

LIST_URL = "https://directwonen.nl/huurwoningen-huren/eindhoven"
DETAIL_RE = re.compile(
    r"/huurwoningen-huren/eindhoven/[^/]+/(?:appartement|woning|kamer|studio)-\d+",
    re.I,
)


def _outdoor(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras"))


def _parse_tile(tile: BeautifulSoup) -> Listing | None:
    link = tile.select_one("a[href*='entityId='], a.inner-content[title], a[href*='/huurwoningen-huren/eindhoven/']")
    href = ""
    title = ""
    if link:
        href = link.get("href") or ""
        title = link.get("title") or link.get_text(" ", strip=True)
    if not href:
        for a in tile.select("a[href]"):
            h = a.get("href") or ""
            if DETAIL_RE.search(h.split("?")[0]):
                href = h
                title = a.get("title") or tile.get_text(" ", strip=True)
                break
    if not href:
        return None

    m = re.search(r"entityId=(\d+)", href)
    if m:
        entity_id = m.group(1)
        ret = re.search(r"returnUrl=([^&]+)", href)
        if ret:
            from urllib.parse import unquote

            href = unquote(ret.group(1))
    else:
        entity_id = re.search(r"-(\d+)(?:\?|$)", href)
        entity_id = entity_id.group(1) if entity_id else href.rstrip("/").split("-")[-1]

    url = href if href.startswith("http") else urljoin("https://directwonen.nl", href.split("?")[0])
    text = tile.get_text(" ", strip=True)
    rent = extract_rent_eur(text)
    size = extract_size_m2(text)
    if not title:
        title = text[:120] or url.rstrip("/").split("/")[-2]
    location = "Eindhoven"
    if "eindhoven" not in title.lower():
        title = f"{title}, Eindhoven"

    return Listing(
        source="directwonen",
        source_id=f"directwonen-{entity_id}",
        title=title[:200],
        url=url,
        location=location,
        rent_eur=rent,
        size_m2=size,
        outdoor_space=_outdoor(text),
        contract_months=None,
        available_from=None,
        notes=text[:500] if text else None,
    )


def fetch_directwonen_eindhoven_listings(list_url: str | None = None) -> list[Listing]:
    base = list_url or os.getenv("DIRECTWONEN_LIST_URL", LIST_URL)
    max_pages = int(os.getenv("DIRECTWONEN_MAX_PAGES", "3"))
    seen: set[str] = set()
    out: list[Listing] = []

    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base.rstrip('/')}?pageno={page}"
        try:
            fetched = fetch_html_with_fallback(url)
        except Exception:
            break
        soup = BeautifulSoup(fetched.html, "html.parser")
        tiles = soup.select("div.tile")
        new = 0
        for tile in tiles:
            listing = _parse_tile(tile)
            if not listing or listing.url in seen:
                continue
            seen.add(listing.url)
            out.append(listing)
            new += 1
        if new == 0 and page > 1:
            break
    return out
