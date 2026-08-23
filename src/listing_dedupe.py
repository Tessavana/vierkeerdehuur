"""Deduplicate rental listings across providers (same home, different URLs)."""

from __future__ import annotations

import re

from rapidfuzz import fuzz


def _norm_url(url: str) -> str:
    return (url or "").strip().lower().split("?")[0].rstrip("/")


def _norm_location(location: str) -> str:
    text = (location or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _listing_key(item: dict) -> tuple:
    rent = item.get("rent_eur")
    size = item.get("size_m2")
    loc = _norm_location(item.get("location") or item.get("title") or "")
    return (loc, rent, size)


def dedupe_listings(items: list[dict]) -> tuple[list[dict], int]:
    """Return unique listings; prefer earlier (usually higher-quality source order)."""
    by_url: list[dict] = []
    seen_urls: set[str] = set()
    url_dupes = 0

    for item in items:
        key = _norm_url(item.get("url") or "")
        if not key:
            continue
        if key in seen_urls:
            url_dupes += 1
            continue
        seen_urls.add(key)
        by_url.append(item)

    out: list[dict] = []
    fuzzy_dupes = 0
    for item in by_url:
        rent = item.get("rent_eur")
        size = item.get("size_m2")
        loc = _norm_location(item.get("location") or item.get("title") or "")
        if rent and size and loc:
            duplicate = False
            for kept in out:
                krent = kept.get("rent_eur")
                ksize = kept.get("size_m2")
                kloc = _norm_location(kept.get("location") or kept.get("title") or "")
                if not krent or not ksize or not kloc:
                    continue
                if abs(krent - rent) <= 50 and abs(ksize - size) <= 5:
                    if fuzz.ratio(kloc, loc) >= 85 or fuzz.partial_ratio(kloc, loc) >= 92:
                        duplicate = True
                        break
            if duplicate:
                fuzzy_dupes += 1
                continue
        out.append(item)

    return out, url_dupes + fuzzy_dupes
