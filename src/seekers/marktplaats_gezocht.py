"""Marktplaats 'gezocht' search — structured via __NEXT_DATA__."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import requests

from src.seekers.common import SeekerPost, post_from_fields

_BASE = "https://www.marktplaats.nl"
_SEARCH = os.getenv(
    "MARKTPLAATS_SEEKER_URL",
    "https://www.marktplaats.nl/q/eindhoven+gezocht+huur/",
)


def _find_listings(obj) -> list[dict]:
    if isinstance(obj, dict):
        if "title" in obj and ("vipUrl" in obj or "itemUrl" in obj):
            return [obj]
        out: list[dict] = []
        for v in obj.values():
            out.extend(_find_listings(v))
        return out
    if isinstance(obj, list):
        out: list[dict] = []
        for v in obj:
            out.extend(_find_listings(v))
        return out
    return []


def _listing_url(item: dict) -> str:
    path = item.get("vipUrl") or item.get("itemUrl") or ""
    if path.startswith("http"):
        return path.split("?")[0]
    return f"{_BASE}{path}".split("?")[0]


def _is_housing_wanted(item: dict) -> bool:
    path = (item.get("vipUrl") or item.get("itemUrl") or "").lower()
    title = (item.get("title") or "").lower()
    if "/huizen-en-kamers/" not in path:
        return False
    if any(x in title for x in ("dj ", "transport", "verhuizer", "opslag")):
        return False
    return any(
        x in title
        for x in ("gezocht", "zoek", "op zoek", "woningruil", "kamer gezocht", "huur gezocht")
    ) or "op-zoek-naar" in path


def fetch_marktplaats_seekers() -> list[SeekerPost]:
    try:
        r = requests.get(
            _SEARCH,
            headers={"User-Agent": "Mozilla/5.0 (compatible; vierkeerdehuur/1.0)"},
            timeout=25,
        )
        if r.status_code >= 400:
            return []
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
            r.text,
            re.S,
        )
        if not m:
            return []
        data = json.loads(m.group(1))
    except (requests.RequestException, json.JSONDecodeError, AttributeError):
        return []

    out: list[SeekerPost] = []
    seen: set[str] = set()
    for item in _find_listings(data):
        if not _is_housing_wanted(item):
            continue
        url = _listing_url(item)
        if not url or url in seen:
            continue
        seen.add(url)
        title = (item.get("title") or "").strip()
        price_info = item.get("price") or {}
        price_cents = price_info.get("cents") if isinstance(price_info, dict) else None
        budget = int(price_cents // 100) if isinstance(price_cents, int) and price_cents else None
        post = post_from_fields(
            id=f"marktplaats-{item.get('itemId') or url.rstrip('/').split('/')[-1]}",
            source="marktplaats",
            kind="seeking",
            title=title,
            snippet=title,
            url=url,
            author="Marktplaats",
            posted_at=datetime.now(timezone.utc).isoformat(),
            budget_eur=budget,
            location_hint="Eindhoven",
            group_name="Marktplaats gezocht",
        )
        if post:
            out.append(post)

    return out[: int(os.getenv("MARKTPLAATS_SEEKER_MAX", "20"))]
