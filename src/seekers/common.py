"""People searching for housing — feed models and classification."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from html import unescape
from typing import Any

_HOUSING_HINTS = (
    "huur",
    "huurwoning",
    "woning",
    "appartement",
    "kamer",
    "studio",
    "huis",
    "room",
    "house",
    "apartment",
    "flat",
    "rent",
    "gezocht",
    "zoek",
    "op zoek",
    "looking for",
    "housemate",
    "huisgenoot",
    "woningruil",
    "te huur",
    "beschikbaar",
    "verhuur",
    "eindhoven",
    "geldrop",
    "best",
    "valken",
    "woensel",
    "strijp",
)

_SEEKING = (
    "op zoek",
    "gezocht",
    "zoek een",
    "zoeken",
    "zoekt ",
    "looking for",
    "searching for",
    "need a room",
    "need an apartment",
    "who can help",
    "wie kan",
    "dringend",
    "urgently",
    "kamer gezocht",
    "woning gezocht",
    "huur gezocht",
    "huis gezocht",
)

_OFFERING = (
    "te huur",
    "for rent",
    "available",
    "beschikbaar",
    "verhuur",
    "room available",
    "kamer te huur",
    "woning te huur",
    "appartement te huur",
    "huis te huur",
    "aanbied",
    "sublet",
    "onderverhuur",
)


@dataclass
class SeekerPost:
    id: str
    source: str  # reddit | marktplaats | facebook
    kind: str  # seeking | offering | unknown
    title: str
    snippet: str
    url: str
    author: str = ""
    posted_at: str | None = None  # ISO UTC
    budget_eur: int | None = None
    location_hint: str = ""
    group_name: str = ""
    relevance_score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_budget(text: str) -> int | None:
    lowered = text.lower()
    for pat in (
        r"€\s*([\d\.\s]{2,6})",
        r"(\d{3,4})\s*€",
        r"max(?:imaal)?\s*€?\s*([\d\.]+)",
        r"budget\s*€?\s*([\d\.]+)",
    ):
        m = re.search(pat, lowered)
        if m:
            digits = re.sub(r"[^\d]", "", m.group(1))
            if digits:
                val = int(digits)
                if 200 <= val <= 5000:
                    return val
    return None


def extract_location_hint(text: str) -> str:
    lowered = text.lower()
    for name in (
        "eindhoven",
        "geldrop",
        "valken",
        "best",
        "helmond",
        "nuenen",
        "son en breugel",
        "waalre",
        "strijp",
        "centrum",
    ):
        if name in lowered:
            return name.title() if name != "strijp" else "Strijp"
    return ""


def is_housing_related(text: str) -> bool:
    blob = text.lower()
    return any(h in blob for h in _HOUSING_HINTS)


def classify_kind(title: str, snippet: str = "") -> str:
    from src.seekers.relevance import _HOUSING_SEEK, _has_strict_housing

    blob = f"{title} {snippet}".lower()
    if not _has_strict_housing(blob) and not any(s in blob for s in _HOUSING_SEEK if "available" not in s):
        if not any(s in blob for s in ("room available", "te huur", "for rent", "accommodation")):
            return "unknown"
    seek = sum(1 for m in _SEEKING if m in blob)
    offer = sum(1 for m in _OFFERING if m in blob)
    if "gezocht" in blob and "te huur" not in blob:
        seek += 2
    if seek > offer:
        return "seeking"
    if offer > seek:
        return "offering"
    return "unknown"


def post_from_fields(**kwargs: Any) -> SeekerPost | None:
    title = (kwargs.get("title") or "").strip()
    snippet = (kwargs.get("snippet") or "").strip()
    if not title and not snippet:
        return None
    combined = f"{title} {snippet}"
    if not is_housing_related(combined):
        return None
    kind = kwargs.get("kind") or classify_kind(title, snippet)
    return SeekerPost(
        id=str(kwargs["id"]),
        source=str(kwargs["source"]),
        kind=kind,
        title=title[:300],
        snippet=snippet[:500],
        url=str(kwargs["url"]),
        author=str(kwargs.get("author") or ""),
        posted_at=kwargs.get("posted_at"),
        budget_eur=kwargs.get("budget_eur") or extract_budget(combined),
        location_hint=kwargs.get("location_hint") or extract_location_hint(combined),
        group_name=str(kwargs.get("group_name") or ""),
        relevance_score=int(kwargs.get("relevance_score") or 0),
    )
