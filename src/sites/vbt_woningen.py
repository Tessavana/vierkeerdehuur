"""VB&T Eindhoven: individual units from eye-move Woningen.xml (primary source)."""

from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import requests

from src.models import Listing

# Page templates mention generic phrases; use project-specific markers only.
_VBT_DEAD_MARKERS = (
    "wonen voor deze woning is niet meer mogelijk",
    "inschrijving gesloten",
    "reactietermijn verstreken",
    "geen inschrijving",
    "momenteel niet beschikbaar",
    "deze woning is verhuurd",
    "woning is verhuurd",
)

VBT_WONINGEN_FEED_URL = "https://vbth.eye-move.nl/export/Woningen.xml"

_UNAVAILABLE_STATUS = (
    "verhuurd",
    "onder optie",
    "optie",
    "bezet",
    "opgezegd",
    "gesloten",
    "niet beschik",
    "archief",
)


def _outdoor(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras", "buitenruimte"))


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-") or "unit"


def _parse_woningen_xml(content: bytes) -> list[Listing]:
    listings: list[Listing] = []
    for _event, elem in ET.iterparse(BytesIO(content), events=("end",)):
        if elem.tag != "Woning":
            continue
        plaats = (elem.findtext("Adres/Plaats") or "").strip()
        if "eindhoven" not in plaats.lower():
            elem.clear()
            continue
        if (elem.findtext("Archief") or "").strip().lower() == "ja":
            elem.clear()
            continue
        if (elem.findtext("Internet") or "").strip().lower() == "nee":
            elem.clear()
            continue
        koop_huur = (elem.findtext("prijzen/KoopHuur") or "").strip().lower()
        if koop_huur and koop_huur != "huur":
            elem.clear()
            continue

        status = (elem.findtext("Status") or "").strip().lower()
        if status and any(w in status for w in _UNAVAILABLE_STATUS):
            elem.clear()
            continue

        rent_raw = elem.findtext("Prijzen/Huur/HuurPrijs") or elem.findtext("prijzen/Huur/HuurPrijs")
        rent = int(rent_raw) if rent_raw and str(rent_raw).isdigit() else None
        size_raw = elem.findtext("Kenmerken/GebruiksoppervlakteWoonfunctie")
        size = int(size_raw) if size_raw and str(size_raw).isdigit() else None
        if rent is None or size is None:
            elem.clear()
            continue

        straat = (elem.findtext("Adres/Straat") or "").strip()
        huisnr = (elem.findtext("Adres/Huisnummer") or "").strip()
        postcode = (elem.findtext("Adres/Postcode") or "").strip()
        deeplink = (elem.findtext("DeeplinkUrl") or "").strip()
        url = deeplink.replace("www.vbtverhuurmakelaars.nl", "vbtverhuurmakelaars.nl")
        if url and not url.startswith("http"):
            url = f"https://vbtverhuurmakelaars.nl{url}"
        if not url:
            url = "https://vbtverhuurmakelaars.nl/huurwoningen-eindhoven"

        street_line = f"{straat} {huisnr}".strip()
        location = ", ".join(p for p in (street_line, postcode, plaats) if p)
        source_id = f"vbt-woning-{_slug(street_line or url)}"
        title = f"{street_line} — {elem.findtext('SoortObject') or 'woning'}".strip(" —")
        avail = (elem.findtext("AanvaardingDatum") or "").strip() or None
        invoer = (elem.findtext("InvoerDatum") or "").strip()
        platform_date = invoer[:10] if invoer and len(invoer) >= 10 else None
        blob = f"{title} {location}"
        listings.append(
            Listing(
                source="vbt",
                source_id=source_id,
                title=title,
                url=url,
                location=location,
                rent_eur=rent,
                size_m2=size,
                outdoor_space=_outdoor(blob),
                contract_months=None,
                    available_from=avail,
                    platform_listed_date=platform_date,
                    notes=(elem.findtext("Status") or "").strip() or None,
                )
        )
        elem.clear()

    dedup: dict[str, Listing] = {}
    for item in listings:
        dedup[item.source_id] = item
    return list(dedup.values())


def _validate_live_urls(listings: list[Listing]) -> list[Listing]:
    flag = os.getenv("VBT_VALIDATE_WONING_URLS", "true").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return listings
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    interval = float(os.getenv("VBT_VALIDATE_INTERVAL", "0.12"))
    kept: list[Listing] = []
    for item in listings:
        try:
            time.sleep(interval)
            r = session.get(item.url, timeout=25)
            if r.status_code == 404:
                continue
            if r.status_code >= 400:
                kept.append(item)
                continue
            lowered = r.text.lower()
            if any(m in lowered for m in _VBT_DEAD_MARKERS):
                continue
            kept.append(item)
        except requests.RequestException:
            kept.append(item)
    return kept


def fetch_vbt_eindhoven_listings(timeout: int = 120) -> list[Listing]:
    cache_path = Path(os.getenv("VBT_WONINGEN_CACHE_PATH", "data/cache/vbt_woningen.xml"))
    ttl = int(os.getenv("VBT_WONINGEN_CACHE_TTL_SECONDS", "0"))
    content: bytes | None = None
    if ttl > 0 and cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < ttl:
            content = cache_path.read_bytes()
    if content is None:
        response = requests.get(
            VBT_WONINGEN_FEED_URL,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        content = response.content
    listings = _parse_woningen_xml(content)
    return _validate_live_urls(listings)
