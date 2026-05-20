"""Geocode listings by postal address via PDOK (Dutch locatieserver)."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

_CACHE_PATH = Path(os.getenv("GEOCODE_CACHE_PATH", "data/geocode_cache.json"))
_PDOK_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
EINDHOVEN_LAT, EINDHOVEN_LON = 51.4416, 5.4697


def _coords_from_item_fields(item: dict[str, Any]) -> tuple[float, float] | None:
    lat, lon = item.get("map_lat"), item.get("map_lon")
    if lat is None or lon is None:
        notes = item.get("notes") or ""
        m_lat = re.search(r"map_lat=([-\d.]+)", notes)
        m_lon = re.search(r"map_lon=([-\d.]+)", notes)
        if m_lat and m_lon:
            try:
                lat, lon = float(m_lat.group(1)), float(m_lon.group(1))
            except ValueError:
                return None
        else:
            return None
    try:
        return round(float(lat), 6), round(float(lon), 6)
    except (TypeError, ValueError):
        return None


def _address_query(item: dict[str, Any]) -> str | None:
    """Build a geocodable address string from listing fields."""
    loc = (item.get("location") or "").strip()
    title = (item.get("title") or "").strip()

    if loc and re.search(r"\d", loc):
        if "eindhoven" not in loc.lower():
            loc = f"{loc}, Eindhoven"
        if "nederland" not in loc.lower() and "netherlands" not in loc.lower():
            loc = f"{loc}, Netherlands"
        return loc

    street = title
    for sep in (" — ", " – ", " | "):
        if sep in title:
            street = title.split(sep, 1)[0].strip()
            break
    if street and re.search(r"\d", street):
        return f"{street}, Eindhoven, Netherlands"

    m = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", f"{title} {loc}")
    if m:
        return f"{m.group(1)} {m.group(2).upper()}, Eindhoven, Netherlands"
    return None


def _load_cache() -> dict[str, list[float]]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return {k: [float(v[0]), float(v[1])] for k, v in raw.items() if isinstance(v, list) and len(v) == 2}
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _pdok_lookup(session: requests.Session, q: str) -> tuple[float, float] | None:
    try:
        time.sleep(float(os.getenv("GEOCODE_INTERVAL", "0.15")))
        r = session.get(
            _PDOK_URL,
            params={"q": q, "rows": 1, "fq": "gemeentenaam:Eindhoven"},
            timeout=15,
        )
        if r.status_code >= 400:
            return None
        docs = r.json().get("response", {}).get("docs", [])
        if not docs:
            r2 = session.get(_PDOK_URL, params={"q": q, "rows": 1}, timeout=15)
            docs = r2.json().get("response", {}).get("docs", [])
        if not docs:
            return None
        centroide = docs[0].get("centroide_ll", "")
        m = re.search(r"POINT\(([-\d.]+)\s+([-\d.]+)\)", centroide)
        if not m:
            return None
        lon, lat = float(m.group(1)), float(m.group(2))
        return round(lat, 6), round(lon, 6)
    except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError):
        return None


def attach_map_coordinates(items: list[dict[str, Any]]) -> None:
    if os.getenv("GEOCODE_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return

    cache = _load_cache()
    session = requests.Session()

    for item in items:
        existing = _coords_from_item_fields(item)
        if existing:
            item["map_lat"], item["map_lon"] = existing
            continue

        q = _address_query(item)
        if not q:
            item["map_lat"], item["map_lon"] = EINDHOVEN_LAT, EINDHOVEN_LON
            continue

        key = q.casefold().strip()
        if key in cache:
            item["map_lat"], item["map_lon"] = cache[key]
            continue

        coords = _pdok_lookup(session, q)
        if coords:
            cache[key] = list(coords)
            item["map_lat"], item["map_lon"] = coords
        else:
            item["map_lat"], item["map_lon"] = EINDHOVEN_LAT, EINDHOVEN_LON

    _save_cache(cache)
