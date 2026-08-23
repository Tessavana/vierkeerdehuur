"""Resolve Eindhoven stadsdeel — only the 7 official names."""

from __future__ import annotations

import re

# Official stadsdelen (Eindhoven gemeente).
OFFICIAL_STADSDELEN: tuple[str, ...] = (
    "Woensel-noord",
    "Woensel-zuid",
    "Strijp",
    "Centrum",
    "Tongelre",
    "Gestel",
    "Stratum",
)

# Postcode prefix -> official stadsdeel.
_POSTCODE_STADSDEEL: dict[str, str] = {
    "5611": "Centrum",
    "5612": "Woensel-zuid",
    "5613": "Strijp",
    "5614": "Strijp",
    "5615": "Strijp",
    "5616": "Gestel",
    "5617": "Strijp",
    "5618": "Gestel",
    "5621": "Woensel-zuid",
    "5622": "Woensel-zuid",
    "5623": "Woensel-zuid",
    "5625": "Woensel-zuid",
    "5626": "Woensel-zuid",
    "5627": "Woensel-zuid",
    "5628": "Woensel-zuid",
    "5629": "Woensel-noord",
    "5630": "Woensel-noord",
    "5631": "Woensel-noord",
    "5632": "Woensel-noord",
    "5633": "Woensel-noord",
    "5641": "Tongelre",
    "5642": "Tongelre",
    "5643": "Tongelre",
    "5644": "Stratum",
    "5645": "Stratum",
    "5646": "Stratum",
    "5651": "Woensel-zuid",
    "5652": "Woensel-zuid",
    "5653": "Woensel-zuid",
    "5654": "Woensel-zuid",
    "5655": "Woensel-zuid",
    "5656": "Woensel-zuid",
    "5657": "Woensel-zuid",
    "5658": "Woensel-zuid",
}

_KEYWORD_STADSDEEL: list[tuple[str, str]] = [
    ("woensel-noord", "Woensel-noord"),
    ("woensel-zuid", "Woensel-zuid"),
    ("meerhoven", "Woensel-noord"),
    ("strijp-s", "Strijp"),
    ("strijp-r", "Strijp"),
    ("strijp", "Strijp"),
    ("oud-strijp", "Strijp"),
    ("centrum", "Centrum"),
    ("regentekwartier", "Centrum"),
    ("tongelre", "Tongelre"),
    ("gestel", "Gestel"),
    ("stratum", "Stratum"),
    ("oud-stratum", "Stratum"),
    ("woensel", "Woensel-zuid"),
]


def extract_postcode(text: str) -> str | None:
    m = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", text or "")
    if m:
        return f"{m.group(1)}{m.group(2).upper()}"
    m2 = re.search(r"\b(\d{4})([A-Za-z]{2})\b", text or "")
    if m2:
        return f"{m2.group(1)}{m2.group(2).upper()}"
    return None


def normalize_stadsdeel(raw: str) -> str:
    """Map any label to one of the 7 official stadsdelen."""
    if not raw:
        return "Centrum"
    key = raw.strip().lower().replace("_", "-")
    for needle, label in _KEYWORD_STADSDEEL:
        if needle in key or key == needle:
            return label
    for official in OFFICIAL_STADSDELEN:
        if official.lower() == key:
            return official
    pc = extract_postcode(raw)
    if pc and pc[:4] in _POSTCODE_STADSDEEL:
        return _POSTCODE_STADSDEEL[pc[:4]]
    return "Centrum"


def stadsdeel_from_postcode(pc: str | None) -> str:
    if not pc or len(pc) < 4:
        return "Centrum"
    return _POSTCODE_STADSDEEL.get(pc[:4], "Centrum")


def resolve_neighborhood(
    title: str = "",
    location: str = "",
    notes: str = "",
    *,
    geocode_wijk: str = "",
) -> str:
    if geocode_wijk:
        return normalize_stadsdeel(geocode_wijk)

    blob = f"{title} {location} {notes or ''}"
    searchable = blob.lower()

    for needle, label in _KEYWORD_STADSDEEL:
        if needle in searchable:
            return label

    pc = extract_postcode(location) or extract_postcode(title) or extract_postcode(notes or "")
    return stadsdeel_from_postcode(pc)
