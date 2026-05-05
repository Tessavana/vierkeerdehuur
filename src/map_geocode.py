"""Attach map_lat/map_lon using OpenStreetMap Nominatim (cached, rate-limited)."""

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
_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "vierkeerdehuur-map/1.0 (+https://github.com/Tessavana/vierkeerdehuur)",
)
_MIN_INTERVAL = float(os.getenv("NOMINATIM_MIN_INTERVAL", "1.1"))
_last_call = 0.0


def _hash_fallback_coords(item: dict[str, Any]) -> tuple[float, float]:
    key = f"{item.get('url', '')}|{item.get('location', '')}|{item.get('title', '')}"
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16)
    dlat = (h % 2000) / 2000 * 0.035 - 0.0175
    dlon = ((h // 2000) % 2000) / 2000 * 0.05 - 0.025
    return round(EINDHOVEN_LAT + dlat, 6), round(EINDHOVEN_LON + dlon, 6)


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
    # Dutch postcode + city (best accuracy)
    m = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", loc)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}, Eindhoven, Netherlands"
    # Street-like prefix before em dash or pipe (many titles: "Street 1 — …")
    for sep in (" — ", " – ", " | ", "|"):
        if sep in title:
            left = title.split(sep, 1)[0].strip()
            if re.search(r"\d", left) and len(left) > 5:
                return f"{left}, Eindhoven, Netherlands"
    # First comma-separated segment often holds street + city line
    if "," in title:
        left = title.split(",", 1)[0].strip()
        if len(left) > 6 and re.search(r"\d", left):
            return f"{left}, Eindhoven, Netherlands"
    return None


def _nominatim_lookup(session: requests.Session, q: str) -> tuple[float, float] | None:
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call = time.monotonic()
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
    """Set map_lat/map_lon: geocode by address/postcode when possible, else stable hash jitter."""
    if os.getenv("GEOCODE_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        for item in items:
            lat, lon = _hash_fallback_coords(item)
            item["map_lat"] = lat
            item["map_lon"] = lon
        return
    cache = _load_cache()
    session = requests.Session()
    for item in items:
        q = _geocode_query_for_item(item)
        if not q:
            lat, lon = _hash_fallback_coords(item)
            item["map_lat"] = lat
            item["map_lon"] = lon
            continue
        key = q.casefold().strip()
        if key in cache:
            lat, lon = cache[key]
            item["map_lat"] = lat
            item["map_lon"] = lon
            continue
        coords = _nominatim_lookup(session, q)
        if coords:
            lat, lon = coords
            cache[key] = [lat, lon]
            item["map_lat"] = lat
            item["map_lon"] = lon
        else:
            lat, lon = _hash_fallback_coords(item)
            item["map_lat"] = lat
            item["map_lon"] = lon
    _save_cache(cache)
