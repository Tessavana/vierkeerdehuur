"""VB&T: listings from public eye-move XML export (full Eindhoven inventory)."""

import os
import re
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import requests

from src.filters import INACTIVE_LISTING_MARKERS
from src.models import Listing

VBT_PROJECT_FEED_URL = "https://vbth.eye-move.nl/export/Projecten.xml"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "unit"


def _outdoor_from_text(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras", "buitenruimte"))


def _parse_vbt_xml_bytes(content: bytes) -> list[Listing]:
    listings: list[Listing] = []
    for _event, elem in ET.iterparse(BytesIO(content), events=("end",)):
        if elem.tag != "Project":
            continue
        plaats = (elem.findtext("Adres/Plaats") or "").strip()
        if "eindhoven" not in plaats.lower():
            elem.clear()
            continue
        if (elem.findtext("Archief") or "").strip().lower() == "ja":
            elem.clear()
            continue
        project_naam = (elem.findtext("Naam") or "").strip() or "VB&T project"
        deeplink = (elem.findtext("DeeplinkUrl") or "").strip()
        m_id = re.search(r"/Project/(\d+)/", deeplink, re.I)
        project_id = m_id.group(1) if m_id else _slug(project_naam)
        postcode = (elem.findtext("Adres/Postcode") or "").strip()
        location = f"{postcode} {plaats}".strip() or plaats
        listing_url = deeplink.replace("www.vbtverhuurmakelaars.nl", "vbtverhuurmakelaars.nl")
        if listing_url and not listing_url.startswith("http"):
            listing_url = f"https://vbtverhuurmakelaars.nl{listing_url}"

        objecttypes = elem.find("Objecttypes")
        if objecttypes is None:
            elem.clear()
            continue
        for ot in objecttypes.findall("Objecttype"):
            type_naam = (ot.findtext("Naam") or "").strip()
            if not type_naam:
                continue
            lowered = type_naam.lower()
            type_obj = (ot.findtext("TypeObject") or "").lower()
            status_parts = " ".join(
                ((ot.findtext(t) or "").strip().lower() for t in ("Status", "Huurstatus", "Verhuurd", "Beschikbaarheid"))
            )
            if status_parts.strip() and any(
                w in status_parts
                for w in ("verhuurd", "niet beschik", "bezet", "opgezegd", "archief", "gesloten")
            ):
                continue
            if "parkeer" in lowered or "parkeerplaats" in type_obj:
                continue
            koop_huur = (ot.findtext("prijzen/KoopHuur") or "").strip().lower()
            if koop_huur != "huur":
                continue
            hv = ot.findtext("prijzen/HuurprijsVan")
            hm = ot.findtext("prijzen/HuurprijsTm")
            wv = ot.findtext("Kenmerken/WoonoppVan")
            wm = ot.findtext("Kenmerken/WoonoppTm")
            vrij = (ot.findtext("Kenmerken/AantalVrijeEenheden") or "").strip()
            if vrij.isdigit() and int(vrij) == 0:
                continue
            if (ot.findtext("Internet") or "").strip().lower() == "nee":
                continue
            rent = int(hv) if hv and hv.isdigit() else None
            if rent is None and hm and hm.isdigit():
                rent = int(hm)
            size = None
            if wv and wv.isdigit():
                size = int(wv)
            elif wm and wm.isdigit():
                size = int(wm)
            source_id = f"vbt-{project_id}-{_slug(type_naam)}"
            title = f"{project_naam} — {type_naam}"
            if hv and hm and hv != hm:
                title = f"{title} (€{hv}–€{hm})"
            blob = f"{title} {location} {project_naam}"
            eenheden = (ot.findtext("Kenmerken/AantalEenheden") or "").strip()
            notes = f"Vrije eenheden: {vrij or '?'} / {eenheden or '?'}" if vrij or eenheden else None
            listings.append(
                Listing(
                    source="vbt",
                    source_id=source_id,
                    title=title,
                    url=listing_url or "https://vbtverhuurmakelaars.nl/huurwoningen-eindhoven",
                    location=location,
                    rent_eur=rent,
                    size_m2=size,
                    outdoor_space=_outdoor_from_text(blob),
                    contract_months=None,
                    available_from=None,
                    notes=notes,
                )
            )
        elem.clear()

    dedup: dict[str, Listing] = {}
    for item in listings:
        dedup[item.source_id] = item
    return list(dedup.values())


_EXTRA_VBT_HTML_MARKERS = (
    "inschrijving gesloten",
    "reactietermijn verstreken",
    "geen inschrijving",
    "momenteel niet beschikbaar",
    "wonen voor deze woning is niet meer mogelijk",
)


def _dead_vbt_project_urls(listings: list[Listing]) -> set[str]:
    flag = os.getenv("VBT_VALIDATE_PROJECT_URLS", "true").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return set()
    by_url: dict[str, list[Listing]] = {}
    for item in listings:
        if "/project/" not in item.url.lower():
            continue
        by_url.setdefault(item.url, []).append(item)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    dead: set[str] = set()
    for url in by_url:
        try:
            time.sleep(float(os.getenv("VBT_VALIDATE_INTERVAL", "0.12")))
            r = session.get(url, timeout=25)
            if r.status_code == 404:
                dead.add(url)
                continue
            if r.status_code >= 400:
                continue
            lowered = r.text.lower()
            if any(m in lowered for m in INACTIVE_LISTING_MARKERS):
                dead.add(url)
                continue
            if any(m in lowered for m in _EXTRA_VBT_HTML_MARKERS):
                dead.add(url)
                continue
        except requests.RequestException:
            continue
    return dead


def fetch_vbt_eindhoven_listings(timeout: int = 120) -> list[Listing]:
    cache_path = Path(os.getenv("VBT_FEED_CACHE_PATH", "data/cache/vbt_projecten.xml"))
    ttl = int(os.getenv("VBT_FEED_CACHE_TTL_SECONDS", "0"))
    content: bytes | None = None
    if ttl > 0 and cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < ttl:
            content = cache_path.read_bytes()
    if content is None:
        response = requests.get(
            VBT_PROJECT_FEED_URL,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        content = response.content
    listings = _parse_vbt_xml_bytes(content)
    dead_urls = _dead_vbt_project_urls(listings)
    if dead_urls:
        listings = [x for x in listings if x.url not in dead_urls]
    return listings
