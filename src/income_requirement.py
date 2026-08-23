"""Extract rental income requirements (inkomenseis) from listing text/HTML."""

from __future__ import annotations

import re
from dataclasses import replace

from bs4 import BeautifulSoup

from src.models import Listing

# Typical range for monthly gross income as a multiple of rent.
_MIN_MULTIPLIER = 2.5
_MAX_MULTIPLIER = 6.0

_MULTIPLIER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:inkomenseis|inkomen(?:seis)?|salaris(?:eis)?|bruto\s+maand(?:inkomen|salaris))"
        r"[^\d]{0,50}?(\d(?:[.,]\d)?)\s*(?:x|×|\*|maal|keer|times)\s*(?:de\s+)?(?:kale\s+)?(?:maand)?huur",
        re.I,
    ),
    re.compile(
        r"(?<![\d./])(\d(?:[.,]\d)?)\s*(?:x|×|\*|maal|keer|times)\s*(?:de\s+)?(?:kale\s+)?(?:maand)?(?:huur|rent)\b",
        re.I,
    ),
    re.compile(
        r"(?:income\s+requirement|requires?\s+income|income\s+requires?)"
        r"[^\d]{0,50}?(\d(?:[.,]\d)?)\s*(?:x|×|\*|maal|times)",
        re.I,
    ),
    re.compile(r"(\d(?:[.,]\d)?)\s*(?:x|×)\s*(?:the\s+)?monthly\s+rent", re.I),
    re.compile(r"(\d)\s*month(?:'s|s|\s)?\s*rent", re.I),
    re.compile(
        r"(\d(?:[.,]\d)?)\s*(?:x|×|\*|maal|keer)\s*(?:het\s+)?bruto\s+maand(?:inkomen|salaris)",
        re.I,
    ),
]

_ANNUAL_FACTOR = re.compile(
    r"(?:bruto\s+)?jaarinkomen[^\d]{0,40}(\d{2,3})\s*(?:x|×|\*|maal|keer)\s*(?:de\s+)?(?:kale\s+)?maandhuur",
    re.I,
)

_ABSOLUTE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:minimaal|minimum|min\.)\s*(?:bruto\s+)?(?:maand(?:inkomen|salaris)|inkomen|salaris)"
        r"[^\d€]{0,24}(?:€|EUR)\s*([\d\.\s]{3,10})",
        re.I,
    ),
    re.compile(
        r"(?:bruto\s+)?(?:maand(?:inkomen|salaris)|inkomen)\s*(?:van\s+)?(?:minimaal\s+)?(?:€|EUR)\s*([\d\.\s]{3,10})",
        re.I,
    ),
    re.compile(
        r"(?:inkomen(?:seis)?|salaris(?:eis)?)[^\d€]{0,30}(?:€|EUR)\s*([\d\.\s]{3,10})",
        re.I,
    ),
]

_GUARANTOR_MARKERS = (
    "garantsteller",
    "garantor",
    "borgsteller",
    "waarborgsteller",
)


def _parse_multiplier(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", ".")
    try:
        val = float(text)
    except ValueError:
        return None
    if _MIN_MULTIPLIER <= val <= _MAX_MULTIPLIER:
        return val
    return None


def _parse_eur(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", raw or "")
    if not digits:
        return None
    val = int(digits)
    if 900 <= val <= 25000:
        return val
    return None


def _format_multiplier(multiplier: float) -> str:
    if abs(multiplier - round(multiplier)) < 0.05:
        return str(int(round(multiplier)))
    return f"{multiplier:.1f}".replace(".", ",")


def _build_label(
    *,
    multiplier: float | None,
    required_eur: int | None,
    rent_eur: int | None,
    has_guarantor: bool,
) -> str | None:
    parts: list[str] = []
    if multiplier is not None:
        parts.append(f"{_format_multiplier(multiplier)}× huur")
    if required_eur is not None:
        parts.append(f"€{required_eur:,}".replace(",", "."))
    if not parts:
        return None
    label = " · ".join(parts)
    if has_guarantor:
        label += " (+ garant)"
    return label


def extract_income_requirement(text: str, *, rent_eur: int | None = None) -> dict:
    """Return income_multiplier, income_required_eur, income_requirement_label."""
    blob = (text or "").replace("\xa0", " ")
    if not blob.strip():
        return {}

    rent = rent_eur if rent_eur is not None and rent_eur >= 300 else None

    has_guarantor = any(m in blob.lower() for m in _GUARANTOR_MARKERS)
    multiplier: float | None = None
    required_eur: int | None = None

    for pattern in _MULTIPLIER_PATTERNS:
        m = pattern.search(blob)
        if not m:
            continue
        multiplier = _parse_multiplier(m.group(1))
        if multiplier is not None:
            break

    if multiplier is None:
        m = _ANNUAL_FACTOR.search(blob)
        if m:
            try:
                annual_x = int(m.group(1))
            except ValueError:
                annual_x = 0
            if 30 <= annual_x <= 60:
                multiplier = round(annual_x / 12.0, 2)

    if required_eur is None:
        for pattern in _ABSOLUTE_PATTERNS:
            m = pattern.search(blob)
            if not m:
                continue
            required_eur = _parse_eur(m.group(1))
            if required_eur is not None:
                break

    if multiplier is not None and rent and required_eur is None:
        required_eur = int(round(rent * multiplier))
    elif required_eur is not None and rent and multiplier is None:
        multiplier = round(required_eur / rent, 2)
        if not (_MIN_MULTIPLIER <= multiplier <= _MAX_MULTIPLIER):
            multiplier = None

    label = _build_label(
        multiplier=multiplier,
        required_eur=required_eur,
        rent_eur=rent,
        has_guarantor=has_guarantor,
    )
    if multiplier is None and required_eur is None:
        return {}

    out: dict = {}
    if multiplier is not None:
        out["income_multiplier"] = multiplier
    if required_eur is not None:
        out["income_required_eur"] = required_eur
    if label:
        out["income_requirement_label"] = label
    if has_guarantor:
        out["income_guarantor_ok"] = True
    return out


def extract_income_requirement_from_html(
    html: str, *, rent_eur: int | None = None, source: str = ""
) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    chunks: list[str] = [soup.get_text(" ", strip=True)]

    for sel in (
        "[class*='inkomen']",
        "[class*='income']",
        "[data-income]",
        "dl",
        "table",
    ):
        for el in soup.select(sel):
            chunk = el.get_text(" ", strip=True)
            if chunk and len(chunk) < 5000:
                chunks.append(chunk)

    combined = " | ".join(chunks)
    return extract_income_requirement(combined, rent_eur=rent_eur)


def attach_income_requirement(listing: Listing) -> Listing:
    if listing.income_multiplier is not None or listing.income_required_eur is not None:
        return listing

    blob = " ".join(
        p for p in (listing.title, listing.location, listing.notes or "") if p
    )
    fields = extract_income_requirement(blob, rent_eur=listing.rent_eur)
    if not fields:
        return listing

    return replace(
        listing,
        income_multiplier=fields.get("income_multiplier"),
        income_required_eur=fields.get("income_required_eur"),
        income_requirement_label=fields.get("income_requirement_label"),
    )
