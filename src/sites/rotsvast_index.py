"""Rotsvast Eindhoven: direct source via wpararius property index API."""

from __future__ import annotations

import os

import requests

from src.models import Listing

ROTSVAST_INDEX_URL = "https://www.rotsvast.nl/wp-json/wpararius/v1/property/index"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_INACTIVE_STATUS = ("verhuurd", "ingetrokken", "archief", "niet beschikbaar")


def _outdoor(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras"))


def fetch_rotsvast_eindhoven_listings(list_url: str | None = None) -> list[Listing]:
    api_url = os.getenv("ROTSVAST_INDEX_URL", ROTSVAST_INDEX_URL)
    r = requests.get(api_url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    payload = r.json()
    props = payload.get("properties") if isinstance(payload, dict) else payload
    if not isinstance(props, list):
        return []

    listings: list[Listing] = []
    for p in props:
        if not isinstance(p, dict):
            continue
        place = str(p.get("place", "")).strip()
        if place.lower() != "eindhoven":
            continue
        status = str(p.get("status", "")).strip().lower()
        if status and any(s in status for s in _INACTIVE_STATUS):
            continue
        url = str(p.get("url", "")).strip()
        if not url:
            continue
        rent_raw = str(p.get("price", "")).replace(".", "").strip()
        rent = int(rent_raw) if rent_raw.isdigit() else None
        size_raw = str(p.get("oppervlakte", "")).strip()
        size = int(size_raw) if size_raw.isdigit() else None
        street = str(p.get("street", "")).strip()
        housenumber = str(p.get("housenumber", "")).strip()
        zipcode = str(p.get("zipcode", "")).strip()
        title = str(p.get("title", "")).strip() or f"{street} {housenumber}, Eindhoven"
        location = ", ".join(
            x for x in (f"{street} {housenumber}".strip(), zipcode, place) if x
        )
        lat = p.get("lat")
        lon = p.get("lng")
        notes_parts = []
        if status:
            notes_parts.append(f"status={p.get('status')}")
        listings.append(
            Listing(
                source="rotsvast",
                source_id=f"rotsvast-{p.get('id', url)}",
                title=title,
                url=url,
                location=location or "Eindhoven",
                rent_eur=rent,
                size_m2=size,
                outdoor_space=_outdoor(f"{title} {p.get('interior', '')}"),
                contract_months=None,
                available_from=None,
                notes="; ".join(notes_parts) if notes_parts else None,
                map_lat=float(lat) if lat not in (None, "", 0, "0") else None,
                map_lon=float(lon) if lon not in (None, "", 0, "0") else None,
            )
        )
    return listings
