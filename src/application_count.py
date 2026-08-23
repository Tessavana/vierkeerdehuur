"""Extract number of applicants / responses shown on listing detail pages."""

from __future__ import annotations

import os
import re
import time
from dataclasses import replace

from bs4 import BeautifulSoup

from src.models import Listing
from src.web_fetch import fetch_html_with_fallback

# Sources where we always try a fresh detail fetch each scan.
_ALWAYS_REFRESH = frozenset({"vbt", "vesteda", "pararius", "funda", "rotsvast", "nmg"})

_PATTERNS: list[tuple[re.Pattern[str], bool]] = [
    (re.compile(r"beschikbaar\s+(\d+)\+", re.I), True),
    (re.compile(r"(\d+)\+\s*(?:reacties|inschrijvingen|responses|applications)", re.I), True),
    (re.compile(r"(\d+)\s+(?:reacties|inschrijvingen)\b", re.I), False),
    (re.compile(r"(\d+)\s+(?:weergaven|views)\b", re.I), False),
    (re.compile(r"(\d+)\s+personen\s+(?:hebben\s+)?(?:gereageerd|reactie)", re.I), False),
    (re.compile(r"interesse\s*[:\s]+(\d+)\+?", re.I), True),
]


def extract_application_count(text: str, *, source: str = "", url: str = "") -> dict:
    blob = (text or "").lower()
    if not blob.strip():
        return {}

    best: dict | None = None
    for pattern, has_plus in _PATTERNS:
        m = pattern.search(blob)
        if not m:
            continue
        try:
            count = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if count < 0 or count > 5000:
            continue
        label = f"{count}+" if has_plus or "+" in m.group(0) else str(count)
        entry = {
            "application_count": count,
            "application_count_label": label,
        }
        if best is None or count > best["application_count"]:
            best = entry

    if best and source == "vbt" and "beschikbaar" not in blob and best["application_count"] < 2:
        return {}
    return best or {}


def extract_application_count_from_html(html: str, *, source: str = "", url: str = "") -> dict:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return extract_application_count(text, source=source, url=url)


def fetch_application_count(url: str, *, source: str = "") -> dict:
    try:
        fetched = fetch_html_with_fallback(url)
        return extract_application_count_from_html(fetched.html, source=source, url=url)
    except Exception:
        return {}


def attach_application_count(listing: Listing, *, force_refresh: bool = False) -> Listing:
    """Refresh applicant count from the live detail page when available."""
    source = (listing.source or "").lower()
    if not force_refresh and listing.application_count is not None:
        return listing
    if not force_refresh and source not in _ALWAYS_REFRESH:
        if listing.notes:
            from_notes = extract_application_count(listing.notes, source=source, url=listing.url)
            if from_notes:
                return replace(
                    listing,
                    application_count=from_notes.get("application_count"),
                    application_count_label=from_notes.get("application_count_label"),
                )
        return listing

    interval = float(os.getenv("APPLICATION_COUNT_INTERVAL", "0.12"))
    if interval > 0:
        time.sleep(interval)

    fields = fetch_application_count(listing.url, source=source)
    if not fields and listing.notes:
        fields = extract_application_count(listing.notes, source=source, url=listing.url)

    if not fields:
        return listing

    return replace(
        listing,
        application_count=fields.get("application_count"),
        application_count_label=fields.get("application_count_label"),
    )
