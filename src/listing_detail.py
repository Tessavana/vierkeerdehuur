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

from src.application_count import extract_application_count_from_html
from src.income_requirement import extract_income_requirement_from_html
from src.extract import extract_location_hint, extract_rent_eur, extract_size_m2, parse_json_ld, parse_posted_date
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


def normalize_available_from(raw: str | None) -> str | None:
    """Normalize to YYYY-MM-DD (European day-month-year input)."""
    if not raw:
        return None
    text = str(raw).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", text, re.I)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    parsed = _parse_available_from(text)
    if parsed and re.match(r"\d{2}-\d{2}-\d{4}", parsed):
        parts = parsed.split("-")
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return parsed


def _parse_available_from(text: str) -> str | None:
    """Rent start date only — avoid matching unrelated numbers."""
    patterns = (
        r"(?:Beschikbaar|Huur)\s+(?:per|vanaf)\s+(\d{1,2}[-/]\d{1,2}[-/](?:\d{2}|\d{4}))",
        r"Ingangsdatum\s*[:\s]+(\d{1,2}[-/]\d{1,2}[-/](?:\d{2}|\d{4}))",
        r"Aanvaarding(?:datum)?\s*[:\s]+(\d{1,2}[-/]\d{1,2}[-/](?:\d{2}|\d{4}))",
        r"(\d{4}-\d{2}-\d{2})",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        raw = m.group(1).replace("/", "-")
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            return raw
        parts = raw.split("-")
        if len(parts) == 3:
            d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{d:02d}-{mo:02d}-{y}"
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
    rel = parse_posted_date(text)
    if rel:
        return rel
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
    structured = parse_json_ld(soup)
    if structured.get("rent_eur") is None:
        structured["rent_eur"] = extract_rent_eur(text)
    if structured.get("size_m2") is None:
        structured["size_m2"] = extract_size_m2(text)
    if not structured.get("location"):
        structured["location"] = extract_location_hint(text)
    if not structured.get("platform_listed_date") and listed:
        structured["platform_listed_date"] = listed.isoformat()
    source = _source_from_url(url)
    app = extract_application_count_from_html(html, source=source, url=url)
    rent = structured.get("rent_eur")
    income = extract_income_requirement_from_html(html, rent_eur=rent, source=source)
    return {
        "description": _extract_description(soup, text),
        "platform_listed_date": structured.get("platform_listed_date"),
        "available_from": _parse_available_from(text),
        "rent_eur": rent,
        "size_m2": structured.get("size_m2"),
        "location": structured.get("location"),
        "application_count": app.get("application_count"),
        "application_count_label": app.get("application_count_label"),
        "income_multiplier": income.get("income_multiplier"),
        "income_required_eur": income.get("income_required_eur"),
        "income_requirement_label": income.get("income_requirement_label"),
    }


def _source_from_url(url: str) -> str:
    lower = (url or "").lower()
    if "vbtverhuurmakelaars" in lower or "vbt" in lower:
        return "vbt"
    if "vesteda.com" in lower:
        return "vesteda"
    if "pararius.com" in lower:
        return "pararius"
    if "funda.nl" in lower:
        return "funda"
    if "rotsvast.nl" in lower:
        return "rotsvast"
    if "nmgwonen.nl" in lower:
        return "nmg"
    return ""


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
    if avail and ("T" in avail or re.match(r"\d{4}-\d{2}-\d{2}T", avail)):
        avail = avail[:10] if re.match(r"\d{4}-\d{2}-\d{2}", avail) else None
    listed_date = fields.get("platform_listed_date")
    rent = listing.rent_eur or fields.get("rent_eur")
    size = listing.size_m2 or fields.get("size_m2")
    location = listing.location
    if location in ("Unknown", "", "Eindhoven") and fields.get("location"):
        loc = str(fields["location"]).strip()
        if loc and loc.lower() != "unknown":
            location = loc

    blob = f"{desc or ''} {notes or ''}".lower()
    outdoor_known = False
    outdoor_space = listing.outdoor_space
    if desc:
        no_outdoor = any(
            p in blob
            for p in (
                "geen balkon",
                "geen tuin",
                "geen terras",
                "zonder buitenruimte",
                "geen buitenruimte",
                "no balcony",
                "no garden",
            )
        )
        yes_outdoor = any(
            k in blob for k in ("balkon", "tuin", "terras", "dakterras", "buitenruimte")
        )
        if no_outdoor:
            outdoor_known = True
            outdoor_space = False
        elif yes_outdoor:
            outdoor_known = True
            outdoor_space = True

    income_multiplier = listing.income_multiplier or fields.get("income_multiplier")
    income_required_eur = listing.income_required_eur or fields.get("income_required_eur")
    income_label = listing.income_requirement_label or fields.get("income_requirement_label")
    if income_multiplier is None and income_required_eur is None and notes:
        from src.income_requirement import extract_income_requirement

        from_notes = extract_income_requirement(notes, rent_eur=rent)
        income_multiplier = from_notes.get("income_multiplier")
        income_required_eur = from_notes.get("income_required_eur")
        income_label = from_notes.get("income_requirement_label")

    return replace(
        listing,
        notes=notes,
        available_from=avail,
        platform_listed_date=listed_date,
        rent_eur=rent,
        size_m2=size,
        location=location,
        application_count=listing.application_count or fields.get("application_count"),
        application_count_label=listing.application_count_label or fields.get("application_count_label"),
        income_multiplier=income_multiplier,
        income_required_eur=income_required_eur,
        income_requirement_label=income_label,
        outdoor_space=outdoor_space,
        outdoor_known=outdoor_known,
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
    if "blauwe loper" in blob:
        return "student_area"
    return None
