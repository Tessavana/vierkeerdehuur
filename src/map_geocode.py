"""Attach map_lat/map_lon: listing coords, PDOK, Nominatim, wijk centroids, then stable jitter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

EINDHOVEN_LAT = 51.4416
EINDHOVEN_LON = 5.4697

_CACHE_PATH = Path(os.getenv("GEOCODE_CACHE_PATH", "data/geocode_cache.json"))
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_PDOK_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "vierkeerdehuur-map/1.0 (+https://github.com/Tessavana/vierkeerdehuur)",
)
_MIN_INTERVAL = float(os.getenv("NOMINATIM_MIN_INTERVAL", "1.1"))
_last_call = 0.0

# Approximate wijk centroids in Eindhoven (lat, lon).
WIJK_CENTROIDS: dict[str, tuple[float, float]] = {
    "strijp": (51.4512, 5.4558),
    "centrum": (51.4416, 5.4697),
    "bergen": (51.4568, 5.4789),
    "vonderkwartier": (51.4345, 5.4921),
    "engelsbergen": (51.4289, 5.5012),
    "schrijversbuurt": (51.4378, 5.4889),
    "meerrijk": (51.4621, 5.4412),
    "blixembosch": (51.4689, 5.4523),
    "stratum": (51.4156, 5.4923),
    "woensel": (51.4723, 5.4689),
    "tongelre": (51.4489, 5.5123),
    "gestel": (51.4123, 5.4456),
    "genneper": (51.4089, 5.4789),
    "vaartbroek": (51.4523, 5.5234),
}


def _hash_fallback_coords(item: dict[str, Any]) -> tuple[float, float]:
    key = f"{item.get('url', '')}|{item.get('location', '')}|{item.get('title', '')}"
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16)
    dlat = (h % 2000) / 2000 * 0.035 - 0.0175
    dlon = ((h // 2000) % 2000) / 2000 * 0.05 - 0.025
    return round(EINDHOVEN_LAT + dlat, 6), round(EINDHOVEN_LON + dlon, 6)


def _wijk_coords(item: dict[str, Any]) -> tuple[float, float] | None:
    neighborhood = (item.get("neighborhood") or "").strip().lower()
    if neighborhood in WIJK_CENTROIDS:
        return WIJK_CENTROIDS[neighborhood]
    searchable = f"{item.get('title', '')} {item.get('location', '')}".lower()
    for key, coords in WIJK_CENTROIDS.items():
        if key in searchable:
            return coords
    return None


def _coords_from_item_fields(item: dict[str, Any]) -> tuple[float, float] | None:
    lat = item.get("map_lat")
    lon = item.get("map_lon")
    if lat is not None and lon is not None:
        try:
            return round(float(lat), 6), round(float(lon), 6)
        except (TypeError, ValueError):
            pass
    notes = item.get("notes") or ""
    m_lat = re.search(r"map_lat=([-\d.]+)", notes)
    m_lon = re.search(r"map_lon=([-\d.]+)", notes)
    if m_lat and m_lon:
        try:
            return round(float(m_lat.group(1)), 6), round(float(m_lon.group(1)), 6)
        except ValueError:
            pass
    return None


def _load_cache() -> dict[str, list[float]]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        out: dict[str, list[float]] = {}
        for k, v in raw.items():
            if isinstance(v, list) and len(v) == 2:
                out[str(k)] = [float(v[0]), float(v[1])]
        return out
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _geocode_query_for_item(item: dict[str, Any]) -> str | None:
    loc = (item.get("location") or "").strip()
    title = (item.get("title") or "").strip()
    m = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", loc) or re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", title)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}, Eindhoven, Netherlands"
    street = loc.split(",")[0].strip() if loc else ""
    if not street or len(street) < 5:
        for sep in (" — ", " – ", " | "):
            if sep in title:
                street = title.split(sep, 1)[0].strip()
                break
    if street and re.search(r"\d", street):
        return f"{street}, Eindhoven, Netherlands"
    return None


def _rate_limit_sleep() -> None:
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call = time.monotonic()


def _pdok_lookup(session: requests.Session, q: str) -> tuple[float, float] | None:
    try:
        r = session.get(
            _PDOK_URL,
            params={"q": q, "rows": 1, "fq": "gemeentenaam:Eindhoven"},
            timeout=15,
        )
        if r.status_code >= 400:
            return None
        docs = r.json().get("response", {}).get("docs", [])
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


def _nominatim_lookup(session: requests.Session, q: str) -> tuple[float, float] | None:
    _rate_limit_sleep()
    r = session.get(
        _NOMINATIM_URL,
        params={"q": q, "format": "json", "limit": 1},
        headers={"User-Agent": _USER_AGENT},
        timeout=20,
    )
    if r.status_code >= 400:
        return None
    data = r.json()
    if not data:
        return None
    lat = data[0].get("lat")
    lon = data[0].get("lon")
    if lat is None or lon is None:
        return None
    return round(float(lat), 6), round(float(lon), 6)


def attach_map_coordinates(items: list[dict[str, Any]]) -> None:
    if os.getenv("GEOCODE_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        for item in items:
            existing = _coords_from_item_fields(item)
            if existing:
                item["map_lat"], item["map_lon"] = existing
            else:
                wijk = _wijk_coords(item)
                if wijk:
                    item["map_lat"], item["map_lon"] = wijk
                else:
                    item["map_lat"], item["map_lon"] = _hash_fallback_coords(item)
        return

    cache = _load_cache()
    session = requests.Session()
    use_pdok = os.getenv("GEOCODE_USE_PDOK", "true").strip().lower() not in {"0", "false", "no", "off"}

    for item in items:
        existing = _coords_from_item_fields(item)
        if existing:
            item["map_lat"], item["map_lon"] = existing
            continue

        q = _geocode_query_for_item(item)
        if q:
            key = q.casefold().strip()
            if key in cache:
                lat, lon = cache[key]
                item["map_lat"], item["map_lon"] = lat, lon
                continue
            coords = _pdok_lookup(session, q) if use_pdok else None
            if not coords:
                coords = _nominatim_lookup(session, q)
            if coords:
                lat, lon = coords
                cache[key] = [lat, lon]
                item["map_lat"], item["map_lon"] = lat, lon
                continue

        wijk = _wijk_coords(item)
        if wijk:
            item["map_lat"], item["map_lon"] = wijk
            continue

        lat, lon = _hash_fallback_coords(item)
        item["map_lat"], item["map_lon"] = lat, lon

    _save_cache(cache)
