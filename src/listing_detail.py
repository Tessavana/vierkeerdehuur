"""Fetch listing detail pages: description, platform publish date, huur vanaf."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from src.filters import NEWCOMER_RESTRICTION_MARKERS, STUDENT_ONLY_MARKERS
from src.models import Listing
from src.web_fetch import HEADERS, fetch_html_with_fallback

_CACHE_PATH = Path(os.getenv("DETAIL_CACHE_PATH", "data/detail_cache.json"))
_AMSTERDAM = ZoneInfo("Europe/Amsterdam")
_TODAY_MARKERS = (
    "vandaag geplaatst",
    "sinds vandaag",
    "nieuw vandaag",
    "vandaag online",
    "geplaatst vandaag",
    "today",
)


def _load_cache() -> dict:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, indent=1, ensure_ascii=True), encoding="utf-8")


def _today_amsterdam() -> date:
    return datetime.now(_AMSTERDAM).date()


def _parse_iso_date(raw: str) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(_AMSTERDAM).date()
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def _parse_available_from(text: str) -> str | None:
    patterns = (
        r"(?:Beschikbaar|Huur)\s+(?:per|vanaf)\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"Ingangsdatum\s*[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})\s*\(beschikbaar",
        r"Aanvaarding(?:datum)?\s*[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"Per\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).replace("/", "-")
    return None


def _parse_platform_listed_date(soup: BeautifulSoup, text: str) -> date | None:
    lowered = text.lower()
    if any(m in lowered for m in _TODAY_MARKERS):
        return _today_amsterdam()

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        objs = data if isinstance(data, list) else [data]
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            for key in ("datePosted", "uploadDate", "datePublished", "availabilityStarts"):
                if key in obj:
                    d = _parse_iso_date(str(obj[key]))
                    if d:
                        return d

    for meta in soup.select("meta[property='article:published_time'], meta[itemprop='datePosted']"):
        content = meta.get("content", "")
        d = _parse_iso_date(content)
        if d:
            return d

    m = re.search(
        r"(?:geplaatst|online\s+sinds|sinds)\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        text,
        re.I,
    )
    if m:
        return _parse_iso_date(m.group(1))

    if re.search(r"\bvandaag\b", lowered) and ("geplaatst" in lowered or "sinds" in lowered or "nieuw" in lowered):
        return _today_amsterdam()
    return None


def _extract_description(soup: BeautifulSoup, text: str) -> str:
    for sel in (
        "[class*='description']",
        "[class*='omschrijving']",
        "#description",
        "section.description",
        "div.listing-detail-description",
        "div.property-description",
    ):
        el = soup.select_one(sel)
        if el:
            chunk = el.get_text(" ", strip=True)
            if len(chunk) > 80:
                return chunk[:4000]
    return text[:4000]


def parse_detail_html(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    listed = _parse_platform_listed_date(soup, text)
    return {
        "description": _extract_description(soup, text),
        "platform_listed_date": listed.isoformat() if listed else None,
        "available_from": _parse_available_from(text),
    }


def fetch_detail_fields(url: str) -> dict:
    try:
        fetched = fetch_html_with_fallback(url)
        return parse_detail_html(fetched.html, url)
    except Exception:
        return {}


def enrich_listing(listing: Listing, use_cache: bool = True) -> Listing:
    url = listing.url.strip()
    cache = _load_cache() if use_cache else {}
    if use_cache and url in cache:
        fields = cache[url]
    else:
        fields = fetch_detail_fields(url)
        if use_cache and fields:
            cache[url] = {**fields, "cached_at": datetime.now(timezone.utc).isoformat()}
            _save_cache(cache)

    desc = fields.get("description") or ""
    notes = listing.notes or ""
    if desc and desc not in notes:
        notes = f"{notes} | {desc}" if notes else desc
    notes = notes[:4000] if notes else None

    avail = listing.available_from or fields.get("available_from")
    listed_date = fields.get("platform_listed_date")

    return replace(
        listing,
        notes=notes,
        available_from=avail,
        platform_listed_date=listed_date,
    )


def is_new_on_platform_today(listing: Listing) -> bool:
    raw = getattr(listing, "platform_listed_date", None)
    if not raw:
        return False
    try:
        return date.fromisoformat(str(raw)[:10]) == _today_amsterdam()
    except ValueError:
        return False


def restriction_reason_from_listing(listing: Listing) -> str | None:
    """Extra check on full description after enrichment."""
    blob = " ".join(
        p
        for p in (
            listing.title,
            listing.location,
            (listing.notes or "")[:4000],
        )
        if p
    ).lower()
    if any(m in blob for m in STUDENT_ONLY_MARKERS):
        return "student_only"
    if any(m in blob for m in NEWCOMER_RESTRICTION_MARKERS):
        return "newcomer_restriction"
    if "student" in blob and any(
        w in blob for w in ("alleen", "uitsluitend", "only", "verplicht", "must be")
    ):
        return "student_only"
    return None
