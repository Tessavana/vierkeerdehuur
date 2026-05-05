"""Vesteda: project links from index, then detail pages (Playwright when needed) for rent/m²."""

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import Listing
from src.web_fetch import fetch_html_with_fallback

VESTEDA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_SKIP_PARTS = ("consumer", "huren-op-maat", "sociale-huurwoning")


def _outdoor_from_text(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras", "balkon"))


def _parse_euro_amounts(text: str) -> list[int]:
    out: list[int] = []
    for m in re.finditer(r"€\s*([\d\.\s]{2,10})", text):
        raw = m.group(1).replace(".", "").replace(" ", "")
        if raw.isdigit():
            val = int(raw)
            if 200 <= val <= 6000:
                out.append(val)
    return out


def _parse_size_m2(text: str) -> int | None:
    m = re.search(r"(\d{2,3})\s*m\s*²", text, re.I)
    if not m:
        m = re.search(r"(\d{2,3})\s*m2\b", text, re.I)
    return int(m.group(1)) if m else None


def _parse_available(text: str) -> str | None:
    patterns = (
        r"Beschikbaar\s+(?:per\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"Ingangsdatum\s*[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})\s*\(beschikbaar",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).replace("/", "-")
    return None


def _project_links(list_url: str) -> list[tuple[str, str]]:
    r = requests.get(list_url, timeout=25, headers=VESTEDA_HEADERS)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    base = str(r.url)
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for a in soup.select("a[href*='/nl/huurwoningen-eindhoven/']"):
        href = (a.get("href") or "").strip()
        if not href or href.rstrip("/") == "/nl/huurwoningen-eindhoven":
            continue
        lower = href.lower()
        if any(s in lower for s in _SKIP_PARTS):
            continue
        full = urljoin("https://www.vesteda.com", href)
        if full in seen:
            continue
        seen.add(full)
        label = a.get_text(" ", strip=True) or full.rsplit("/", 1)[-1]
        out.append((full, label))
    return out


def fetch_vesteda_eindhoven_listings(list_url: str, max_detail_pages: int = 18) -> list[Listing]:
    links = _project_links(list_url)[:max_detail_pages]
    listings: list[Listing] = []
    for url, label in links:
        fetched = fetch_html_with_fallback(url)
        soup = BeautifulSoup(fetched.html, "html.parser")
        h1 = soup.select_one("h1")
        title = h1.get_text(" ", strip=True) if h1 else label
        text = soup.get_text(" ", strip=True)
        amounts = _parse_euro_amounts(text)
        rent = min(amounts) if amounts else None
        size = _parse_size_m2(text)
        avail = _parse_available(text)
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        listings.append(
            Listing(
                source="vesteda",
                source_id=f"vesteda-{slug}",
                title=title,
                url=url,
                location="Eindhoven",
                rent_eur=rent,
                size_m2=size,
                outdoor_space=_outdoor_from_text(text),
                contract_months=None,
                available_from=avail,
                notes=text[:1800] if text else None,
            )
        )
    return listings
