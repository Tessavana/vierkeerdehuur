"""VB&T: listings from public eye-move XML export (full Eindhoven inventory)."""

import os
import re
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import requests

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


def fetch_vbt_eindhoven_listings(timeout: int = 120) -> list[Listing]:
    cache_path = Path(os.getenv("VBT_FEED_CACHE_PATH", "data/cache/vbt_projecten.xml"))
    ttl = int(os.getenv("VBT_FEED_CACHE_TTL_SECONDS", "0"))
    if ttl > 0 and cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < ttl:
            return _parse_vbt_xml_bytes(cache_path.read_bytes())

    response = requests.get(
        VBT_PROJECT_FEED_URL,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return _parse_vbt_xml_bytes(response.content)
