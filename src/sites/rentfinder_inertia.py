"""RentFinder: Eindhoven listings via Inertia JSON (price, m², availability in API)."""

import json
import os
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.models import Listing

RF_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _outdoor_from_text(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras"))


def _rentfinder_inertia_version(session: requests.Session) -> str:
    r = session.get("https://rentfinder.nl/properties", timeout=25, headers=RF_HEADERS)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    dp = soup.find("div", attrs={"id": "app", "data-page": True})
    if not dp or not dp.get("data-page"):
        raise RuntimeError("Rentfinder: missing Inertia data-page")
    page = json.loads(dp["data-page"])
    return str(page["version"])


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip().replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else None


def fetch_rentfinder_eindhoven_listings(max_pages: int | None = None) -> list[Listing]:
    if max_pages is None:
        max_pages = int(os.getenv("RENTFINDER_MAX_PAGES", "30"))
    session = requests.Session()
    session.headers.update(RF_HEADERS)
    version = _rentfinder_inertia_version(session)
    inertia_headers = {
        **RF_HEADERS,
        "X-Inertia": "true",
        "X-Inertia-Version": version,
        "Accept": "application/json, text/html, application/xhtml+xml",
    }
    listings: list[Listing] = []
    page = 1
    last_page = 1

    while page <= last_page and page <= max_pages:
        url = f"https://rentfinder.nl/properties?place=Eindhoven&page={page}"
        r = session.get(url, timeout=25, headers=inertia_headers)
        r.raise_for_status()
        payload = r.json()
        block = payload.get("props", {}).get("properties") or {}
        meta = block.get("meta") or {}
        last_page = int(meta.get("last_page") or 1)
        rows = block.get("data") or []
        for row in rows:
            slug = row.get("slug") or ""
            if not slug:
                continue
            if row.get("deleted_at"):
                continue
            status = (row.get("status") or row.get("availability") or "").strip().lower()
            if status in {"rented", "verhuurd", "unavailable", "inactive", "archived"}:
                continue
            title = (row.get("title") or "").strip() or slug
            place = (row.get("place") or "").strip()
            street = (row.get("street") or "").strip()
            location = f"{street}, {place}".strip(", ").strip() if street else (place or "Eindhoven")
            details = row.get("property_details") or {}
            size = _parse_int(details.get("living_area"))
            rent = _parse_int(row.get("price"))
            avail = (row.get("available_at") or "").strip() or None
            desc = (row.get("description") or "").strip()
            notes = f"{desc} {details}".strip()[:2500] or None
            listings.append(
                Listing(
                    source="rentfinder",
                    source_id=f"rentfinder-{row.get('id', slug)}",
                    title=title,
                    url=f"https://rentfinder.nl/properties/{slug}",
                    location=location,
                    rent_eur=rent,
                    size_m2=size,
                    outdoor_space=_outdoor_from_text(title + " " + str(details)),
                    contract_months=None,
                    available_from=avail,
                    notes=notes,
                )
            )
        page += 1

    dedup: dict[str, Listing] = {}
    for item in listings:
        dedup[item.source_id] = item
    return list(dedup.values())
