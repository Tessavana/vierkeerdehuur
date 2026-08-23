"""Resolve Eindhoven wijk from listing address text (title, location, notes)."""

from __future__ import annotations

import re

from src.eindhoven_geo import _POSTCODE_WIJK

# Longer phrases first.
_KEYWORD_WIJK: list[tuple[str, str]] = [
    ("strijp-s", "Strijp-S"),
    ("strijp-r", "Strijp-R"),
    ("blixembosch-buiten", "Blixembosch"),
    ("blixembosch", "Blixembosch"),
    ("regentekwartier", "Centrum"),
    ("het regentekwartier", "Centrum"),
    ("oud-strijp", "Oud-Strijp"),
    ("oud-stratum", "Oud-Stratum"),
    ("meerhoven", "Meerhoven"),
    ("tivoli", "Tivoli"),
    ("picuskade", "Woensel"),
    ("strijp", "Strijp"),
    ("woensel", "Woensel"),
    ("tongelre", "Tongelre"),
    ("gestel", "Gestel"),
    ("stratum", "Stratum"),
    ("centrum", "Centrum"),
    ("meerrijk", "Meerrijk"),
    ("bergen", "Bergen"),
    ("vonderkwartier", "Vonderkwartier"),
    ("engelsbergen", "Engelsbergen"),
    ("schrijversbuurt", "Schrijversbuurt"),
    ("genneper", "Genneper"),
    ("vaartbroek", "Vaartbroek"),
    ("rijpelberg", "Gestel"),
    ("hartje rio", "Gestel"),
    ("next stadsdeel", "Strijp-S"),
]

_WIJK_IN_TEXT = re.compile(
    r"(?:gelegen\s+in\s+(?:de\s+)?wijk|wijk)\s+([A-Za-zÀ-ÿ\-'\s]{3,40})",
    re.I,
)


def extract_postcode(text: str) -> str | None:
    m = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", text or "")
    if m:
        return f"{m.group(1)}{m.group(2).upper()}"
    m2 = re.search(r"\b(\d{4})([A-Za-z]{2})\b", text or "")
    if m2:
        return f"{m2.group(1)}{m2.group(2).upper()}"
    return None


def wijk_from_postcode(pc: str | None) -> str:
    if not pc or len(pc) < 4:
        return ""
    prefix = pc[:4]
    if prefix in _POSTCODE_WIJK:
        return _POSTCODE_WIJK[prefix]
    # Eindhoven ranges not in BAG lookup table.
    try:
        n = int(prefix)
    except ValueError:
        return ""
    if 5611 <= n <= 5617:
        if n in {5616, 5617}:
            return "Gestel" if n == 5616 else "Strijp-S"
        if n in {5613, 5614, 5615}:
            return "Strijp"
        return "Centrum" if n == 5611 else "Woensel"
    if 5627 <= n <= 5633:
        return "Woensel"
    if 5629 <= n <= 5630:
        return "Meerhoven"
    if 5641 <= n <= 5646:
        return "Tongelre"
    if 5651 <= n <= 5658:
        return "Woensel"
    return ""


def resolve_neighborhood(
    title: str = "",
    location: str = "",
    notes: str = "",
    *,
    geocode_wijk: str = "",
) -> str:
    if (geocode_wijk or "").strip():
        return geocode_wijk.strip()

    blob = f"{title} {location} {notes or ''}"
    searchable = blob.lower()

    m = _WIJK_IN_TEXT.search(blob)
    if m:
        raw = m.group(1).strip().split(".")[0].split(",")[0].strip()
        if raw and len(raw) < 40:
            return raw.title()

    for needle, label in _KEYWORD_WIJK:
        if needle in searchable:
            return label

    pc = extract_postcode(location) or extract_postcode(title) or extract_postcode(notes or "")
    from_pc = wijk_from_postcode(pc)
    if from_pc:
        return from_pc

    return "Eindhoven"
