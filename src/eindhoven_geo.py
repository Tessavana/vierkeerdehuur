"""Eindhoven geocoding + wijk from PDOK (postcode/address lookup)."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

_PDOK_FREE = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
_CACHE = Path(os.getenv("GEOCODE_CACHE_PATH", "data/geocode_cache.json"))

# Fallback: eerste 4 cijfers postcode → wijk (Eindhoven).
_POSTCODE_WIJK: dict[str, str] = {
    "5611": "Woensel",
    "5612": "Woensel",
    "5613": "Strijp",
    "5614": "Strijp",
    "5615": "Strijp",
    "5616": "Gestel",
    "5621": "Woensel",
    "5622": "Woensel",
    "5623": "Woensel",
    "5625": "Woensel",
    "5626": "Woensel",
    "5627": "Woensel",
    "5628": "Woensel",
    "5631": "Woensel",
    "5632": "Woensel",
    "5633": "Woensel",
    "5641": "Tongelre",
    "5642": "Tongelre",
    "5643": "Tongelre",
    "5644": "Tongelre",
    "5645": "Tongelre",
    "5646": "Tongelre",
    "5651": "Woensel",
    "5652": "Woensel",
    "5653": "Woensel",
    "5654": "Woensel",
    "5655": "Woensel",
    "5656": "Woensel",
    "5657": "Woensel",
    "5658": "Woensel",
}


def _load_cache() -> dict:
    if not _CACHE.exists():
        return {}
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _extract_postcode(text: str) -> str | None:
    m = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", text)
    if m:
        return f"{m.group(1)}{m.group(2).upper()}"
    return None


def _street_line(item: dict[str, Any]) -> str:
    loc = (item.get("location") or "").strip()
    title = (item.get("title") or "").strip()
    if loc and re.search(r"\d", loc):
        return loc.split(",")[0].strip()
    for sep in (" — ", " – ", " | "):
        if sep in title:
            left = title.split(sep, 1)[0].strip()
            if re.search(r"\d", left):
                return left
    return title if re.search(r"\d", title) else ""


def _query_pdok(session: requests.Session, q: str) -> dict | None:
    time.sleep(float(os.getenv("GEOCODE_INTERVAL", "0.12")))
    try:
        r = session.get(
            _PDOK_FREE,
            params={"q": q, "rows": 1, "fq": "gemeentenaam:Eindhoven"},
            timeout=20,
        )
        if r.status_code >= 400:
            return None
        docs = r.json().get("response", {}).get("docs", [])
        if docs:
            return docs[0]
        r2 = session.get(_PDOK_FREE, params={"q": q, "rows": 1}, timeout=20)
        docs = r2.json().get("response", {}).get("docs", [])
        return docs[0] if docs else None
    except (requests.RequestException, json.JSONDecodeError, KeyError, TypeError):
        return None


def _wijk_from_doc(doc: dict) -> str:
    for key in ("wijknaam", "buurtnaam", "woonplaatsnaam"):
        val = (doc.get(key) or "").strip()
        if val and val.lower() != "eindhoven":
            return val.title()
    pc = (doc.get("postcode") or "").strip()[:4]
    if pc in _POSTCODE_WIJK:
        return _POSTCODE_WIJK[pc]
    return ""


def _coords_from_doc(doc: dict) -> tuple[float, float] | None:
    centroide = doc.get("centroide_ll", "")
    m = re.search(r"POINT\(([-\d.]+)\s+([-\d.]+)\)", centroide)
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return round(lat, 6), round(lon, 6)


def resolve_location(item: dict[str, Any]) -> tuple[float, float, str]:
    """Return (lat, lon, wijk_label) for a listing."""
    notes = item.get("notes") or ""
    m_lat = re.search(r"map_lat=([-\d.]+)", notes)
    m_lon = re.search(r"map_lon=([-\d.]+)", notes)
    if m_lat and m_lon:
        try:
            wijk = (item.get("neighborhood") or "").strip()
            return float(m_lat.group(1)), float(m_lon.group(1)), wijk
        except ValueError:
            pass

    loc_blob = f"{item.get('location', '')} {item.get('title', '')}"
    pc = _extract_postcode(loc_blob)
    street = _street_line(item)
    queries: list[str] = []
    if street and pc:
        queries.append(f"{street}, {pc[:4]} {pc[4:]} Eindhoven")
    if street:
        queries.append(f"{street}, Eindhoven, Netherlands")
    if pc:
        queries.append(f"{pc[:4]} {pc[4:]}, Eindhoven")

    cache = _load_cache()
    session = requests.Session()

    for q in queries:
        key = q.casefold().strip()
        if key in cache:
            entry = cache[key]
            if isinstance(entry, dict):
                return entry["lat"], entry["lon"], entry.get("wijk", "")
            if isinstance(entry, list) and len(entry) == 2:
                return entry[0], entry[1], ""

        doc = _query_pdok(session, q)
        if not doc:
            continue
        coords = _coords_from_doc(doc)
        if not coords:
            continue
        lat, lon = coords
        wijk = _wijk_from_doc(doc)
        if not wijk and pc:
            wijk = _POSTCODE_WIJK.get(pc[:4], "")
        cache[key] = {"lat": lat, "lon": lon, "wijk": wijk}
        _save_cache(cache)
        return lat, lon, wijk

    if pc:
        wijk = _POSTCODE_WIJK.get(pc[:4], "")
        return 51.4416, 5.4697, wijk
    return 51.4416, 5.4697, ""


def attach_map_coordinates(items: list[dict[str, Any]]) -> None:
    if os.getenv("GEOCODE_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return
    for item in items:
        lat, lon, wijk = resolve_location(item)
        item["map_lat"] = lat
        item["map_lon"] = lon
        if wijk:
            item["neighborhood"] = wijk
