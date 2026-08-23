"""Verify listing URLs still point to live rental pages."""

from __future__ import annotations

import os
import re
import time
from typing import Any

import requests

_COMMON_DEAD = (
    "niet meer beschikbaar",
    "niet langer beschikbaar",
    "deze advertentie is verwijderd",
    "advertentie niet gevonden",
    "woning is verhuurd",
    "is verhuurd",
    "reeds verhuurd",
    "aanmelding gesloten",
    "inschrijving gesloten",
    "geen woning gevonden",
    "pagina niet gevonden",
    "404 not found",
    "page not found",
    "niet beschikbaar",
    "verhuurd",
    "archief",
)

_SOURCE_DEAD: dict[str, tuple[str, ...]] = {
    "rentfinder": (
        "property not found",
        "niet gevonden",
        "is verhuurd",
        "niet meer beschikbaar",
    ),
    "vbt": (
        "niet beschikbaar",
        "verhuurd",
        "deze woning is niet meer beschikbaar",
        "woning is verhuurd",
    ),
    "huurwoningen": _COMMON_DEAD,
    "pararius": (
        "niet meer beschikbaar",
        "deze woning is verhuurd",
        "advertentie is offline",
    ),
}

_HEADERS = {"User-Agent": "vierkeerdehuur/1.0 (listing liveness check)"}


def _dead_markers(source: str) -> tuple[str, ...]:
    key = (source or "").lower()
    extra = _SOURCE_DEAD.get(key, ())
    return _COMMON_DEAD + extra


def url_looks_alive(url: str, source: str = "", timeout: float = 12.0) -> bool:
    """Return False when URL is clearly dead (404, gone, verhuurd markers)."""
    if not url or not url.startswith("http"):
        return False
    try:
        resp = requests.get(
            url,
            headers=_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException:
        return False

    if resp.status_code in {404, 410, 451}:
        return False
    if resp.status_code >= 500:
        return True  # site glitch, keep listing

    text = resp.text[:120_000].lower()
    markers = _dead_markers(source)
    hits = sum(1 for m in markers if m in text)
    # Require at least one strong marker, or multiple weak ones for "verhuurd"
    if "niet meer beschikbaar" in text or "advertentie is verwijderd" in text:
        return False
    if hits >= 2 and any(m in text for m in ("verhuurd", "niet beschikbaar", "archief")):
        return False
    if source == "rentfinder" and "property not found" in text:
        return False
    return True


def filter_alive_listings(items: list[dict[str, Any]], *, enabled: bool | None = None) -> tuple[list[dict], int]:
    """Drop listings whose URL fails liveness check. Returns (alive, removed_count)."""
    if enabled is None:
        enabled = os.getenv("LISTING_LIVENESS_CHECK", "true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
    if not enabled or not items:
        return items, 0

    interval = float(os.getenv("LISTING_LIVENESS_INTERVAL", "0.15"))
    alive: list[dict] = []
    removed = 0
    for item in items:
        url = (item.get("url") or "").strip()
        source = item.get("source") or ""
        if url_looks_alive(url, source):
            alive.append(item)
        else:
            removed += 1
            print(f"liveness: dropped dead URL ({source}): {url[:80]}")
        if interval > 0:
            time.sleep(interval)
    return alive, removed
