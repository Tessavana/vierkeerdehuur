"""Eindhoven geocoding + wijk from PDOK (BAG address) with Nominatim fallback."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

_PDOK_FREE = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_CACHE = Path(os.getenv("GEOCODE_CACHE_PATH", "data/geocode_cache.json"))
_CITY_CENTER = (51.4416, 5.4697)

_POSTCODE_WIJK: dict[str, str] = {
    "5611": "Centrum",
    "5612": "Woensel",
    "5613": "Strijp",
    "5614": "Strijp",
    "5615": "Strijp",
    "5616": "Gestel",
    "5617": "Strijp-S",
    "5618": "Gestel",
    "5629": "Meerhoven",
    "5630": "Meerhoven",
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
    m2 = re.search(r"\b(\d{4})([A-Za-z]{2})\b", text)
    if m2:
        return f"{m2.group(1)}{m2.group(2).upper()}"
    return None


def _parse_address(item: dict[str, Any]) -> tuple[str, str, str | None]:
    """Return (street, house_number, postcode)."""
    blob = " ".join(
        p
        for p in (
            item.get("location") or "",
            item.get("title") or "",
            (item.get("notes") or "")[:1200],
        )
        if p
    )
    pc = _extract_postcode(blob)

    loc = (item.get("location") or "").strip()
    title = (item.get("title") or "").strip()

    for raw in (loc, title.split("—")[0].split("–")[0].strip(), title):
        if not raw:
            continue
        m = re.match(
            r"^([A-Za-zÀ-ÿ\s\.\-']+?)\s+(\d+[A-Za-z0-9\-]*(?:\s*[-/]\s*\d+[A-Za-z0-9\-]*)?)\b",
            raw.strip(),
        )
        if m:
            return m.group(1).strip(), m.group(2).strip().replace(" ", ""), pc
        parts = [p.strip() for p in raw.split(",")]
        if parts and re.search(r"\d", parts[0]):
            m2 = re.match(r"^(.+?)\s+(\d+[A-Za-z0-9\-]*)$", parts[0])
            if m2:
                return m2.group(1).strip(), m2.group(2).strip(), pc
        if parts and not re.search(r"\d", parts[0]):
            return parts[0], "", pc

    return "", "", pc


def _wijk_from_doc(doc: dict) -> str:
    for key in ("wijknaam", "buurtnaam"):
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


def _query_pdok(session: requests.Session, q: str, *, adres_only: bool = False) -> dict | None:
    time.sleep(float(os.getenv("GEOCODE_INTERVAL", "0.12")))
    params: dict[str, Any] = {"q": q, "rows": 3, "fq": "gemeentenaam:Eindhoven"}
    if adres_only:
        params["fq"] = "type:adres AND gemeentenaam:Eindhoven"
    try:
        r = session.get(_PDOK_FREE, params=params, timeout=20)
        if r.status_code >= 400:
            return None
        docs = r.json().get("response", {}).get("docs", [])
        for doc in docs:
            if doc.get("type") == "adres" or not adres_only:
                coords = _coords_from_doc(doc)
                if coords:
                    return doc
        return docs[0] if docs else None
    except (requests.RequestException, json.JSONDecodeError, KeyError, TypeError):
        return None


def _query_nominatim(session: requests.Session, q: str) -> tuple[float, float] | None:
    time.sleep(1.05)
    try:
        r = session.get(
            _NOMINATIM,
            params={"q": q, "format": "json", "limit": 1, "countrycodes": "nl"},
            headers={"User-Agent": "vierkeerdehuur-housing/1.0 (eindhoven rental dashboard)"},
            timeout=20,
        )
        if r.status_code >= 400:
            return None
        rows = r.json()
        if not rows:
            return None
        return round(float(rows[0]["lat"]), 6), round(float(rows[0]["lon"]), 6)
    except (requests.RequestException, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _postcode_centroid(session: requests.Session, pc: str, cache: dict) -> tuple[float, float] | None:
    key = f"pc:{pc}"
    if key in cache and isinstance(cache[key], dict):
        return cache[key]["lat"], cache[key]["lon"]
    spaced = f"{pc[:4]} {pc[4:]}"
    doc = _query_pdok(session, f"{spaced}, Eindhoven", adres_only=False)
    if doc:
        coords = _coords_from_doc(doc)
        if coords:
            cache[key] = {"lat": coords[0], "lon": coords[1], "wijk": _wijk_from_doc(doc)}
            _save_cache(cache)
            return coords
    return None


def _jitter_from_url(url: str, lat: float, lon: float) -> tuple[float, float]:
    """Spread listings that only share postcode centroid."""
    h = hashlib.md5(url.encode()).hexdigest()
    a = int(h[:8], 16) / 0xFFFFFFFF * 2 * 3.14159
    r = 0.0012 + (int(h[8:12], 16) / 0xFFFF) * 0.002
    import math

    return round(lat + math.sin(a) * r, 6), round(lon + math.cos(a) * r, 6)


def resolve_location(item: dict[str, Any]) -> tuple[float, float, str]:
    """Return (lat, lon, wijk_label) for a listing."""
    if item.get("map_lat") is not None and item.get("map_lon") is not None:
        try:
            lat, lon = float(item["map_lat"]), float(item["map_lon"])
            wijk = (item.get("neighborhood") or "").strip()
            if lat != _CITY_CENTER[0] or lon != _CITY_CENTER[1]:
                return lat, lon, wijk
        except (TypeError, ValueError):
            pass

    url = (item.get("url") or "").strip()
    cache = _load_cache()
    if url and url in cache:
        entry = cache[url]
        if isinstance(entry, dict) and "lat" in entry:
            return entry["lat"], entry["lon"], entry.get("wijk", "")

    street, number, pc = _parse_address(item)
    session = requests.Session()
    queries: list[tuple[str, bool]] = []

    if street and number and pc:
        queries.append((f"{street} {number}, {pc[:4]} {pc[4:]}, Eindhoven", True))
    if street and number:
        queries.append((f"{street} {number}, Eindhoven, Netherlands", True))
    if street and pc:
        queries.append((f"{street}, {pc[:4]} {pc[4:]}, Eindhoven", True))
    if street:
        queries.append((f"{street}, Eindhoven, Netherlands", False))
    if pc:
        queries.append((f"{pc[:4]} {pc[4:]}, Eindhoven", False))

    wijk = ""
    for q, adres_only in queries:
        doc = _query_pdok(session, q, adres_only=adres_only)
        if not doc:
            coords = _query_nominatim(session, q + ", Netherlands")
            if not coords:
                continue
            lat, lon = coords
            if pc:
                wijk = _POSTCODE_WIJK.get(pc[:4], "")
        else:
            coords = _coords_from_doc(doc)
            if not coords:
                continue
            lat, lon = coords
            wijk = _wijk_from_doc(doc) or _POSTCODE_WIJK.get((pc or "")[:4], "")

        if url:
            cache[url] = {"lat": lat, "lon": lon, "wijk": wijk}
            _save_cache(cache)
        return lat, lon, wijk

    if pc:
        centroid = _postcode_centroid(session, pc, cache)
        wijk = _POSTCODE_WIJK.get(pc[:4], "")
        if centroid:
            lat, lon = _jitter_from_url(url or street, centroid[0], centroid[1])
            if url:
                cache[url] = {"lat": lat, "lon": lon, "wijk": wijk}
                _save_cache(cache)
            return lat, lon, wijk

    lat, lon = _CITY_CENTER
    if url:
        lat, lon = _jitter_from_url(url, lat, lon)
        cache[url] = {"lat": lat, "lon": lon, "wijk": wijk}
        _save_cache(cache)
    return lat, lon, wijk


def attach_map_coordinates(items: list[dict[str, Any]]) -> None:
    if os.getenv("GEOCODE_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return
    from src.neighborhood import resolve_neighborhood

    for item in items:
        lat, lon, wijk = resolve_location(item)
        item["map_lat"] = lat
        item["map_lon"] = lon
        item["neighborhood"] = resolve_neighborhood(
            item.get("title") or "",
            item.get("location") or "",
            item.get("notes") or "",
            geocode_wijk=wijk or item.get("neighborhood") or "",
        )
