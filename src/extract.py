"""Shared listing field extraction from HTML/text/JSON-LD."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

_AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def extract_rent_eur(text: str) -> int | None:
    amounts: list[int] = []
    for m in re.finditer(r"[€\u20ac]\s*([\d\.\s]{2,10})", text or ""):
        raw = re.sub(r"[^\d]", "", m.group(1))
        if raw.isdigit():
            val = int(raw)
            if 200 <= val <= 8000:
                amounts.append(val)
    if not amounts:
        m = re.search(r"(\d{3,4})\s*(?:euro|eur)\b", (text or "").lower())
        if m:
            val = int(m.group(1))
            if 200 <= val <= 8000:
                amounts.append(val)
    return min(amounts) if amounts else None


def extract_size_m2(text: str) -> int | None:
    blob = (text or "").lower()
    for pat in (
        r"(\d{2,3})\s*m\s*²",
        r"(\d{2,3})\s*m2\b",
        r"(\d{2,3})\s*m\b",
    ):
        m = re.search(pat, blob)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 500:
                return val
    return None


def extract_location_hint(text: str, *, default: str = "Eindhoven") -> str:
    blob = text or ""
    pc = re.search(r"\b(\d{4})\s*([A-Za-z]{2})\b", blob)
    if pc:
        street = re.search(
            r"([A-Za-z\u00c0-\u017f][\w\s\-']{2,40}\d{0,4})\s*,?\s*"
            + re.escape(pc.group(1)),
            blob,
        )
        if street:
            return f"{street.group(1).strip()}, {pc.group(1)} {pc.group(2).upper()}, Eindhoven"
        return f"{pc.group(1)} {pc.group(2).upper()}, Eindhoven"
    if "eindhoven" in blob.lower():
        return default
    return default


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


def _parse_relative_posted(text: str) -> date | None:
    lowered = (text or "").lower()
    today = _today_amsterdam()
    if re.search(r"\bposted\s+(?:just now|today)\b", lowered):
        return today
    if re.search(r"\b(?:geplaatst|posted)\s+vandaag\b", lowered):
        return today
    m = re.search(r"(?:posted|geplaatst)\s+(\d+)\s+(minute|hour|day|min|uur|dag)", lowered)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("min"):
            return today
        if unit.startswith("hour") or unit.startswith("uur"):
            return today if n < 48 else today - timedelta(days=1)
        if unit.startswith("day") or unit.startswith("dag"):
            return today - timedelta(days=n)
    m = re.search(r"(\d+)\s+(?:hours?|uur)\s+ago", lowered)
    if m:
        return today
    m = re.search(r"(\d+)\s+(?:days?|dagen)\s+ago", lowered)
    if m:
        return today - timedelta(days=int(m.group(1)))
    return None


def parse_json_ld(soup: BeautifulSoup) -> dict:
    out: dict = {}
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
            types = obj.get("@type")
            type_list = types if isinstance(types, list) else [types]
            if not any(t in ("Apartment", "House", "Residence", "Product", "Offer", "SingleFamilyResidence") for t in type_list if t):
                continue
            for key in ("datePosted", "uploadDate", "datePublished"):
                if key in obj and not out.get("platform_listed_date"):
                    d = _parse_iso_date(str(obj[key]))
                    if d:
                        out["platform_listed_date"] = d.isoformat()
            offers = obj.get("offers")
            if isinstance(offers, dict):
                offers = [offers]
            if isinstance(offers, list):
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    price = offer.get("price")
                    if price is not None and out.get("rent_eur") is None:
                        digits = re.sub(r"[^\d]", "", str(price))
                        if digits.isdigit():
                            val = int(digits)
                            if 200 <= val <= 8000:
                                out["rent_eur"] = val
            if obj.get("floorSize") and out.get("size_m2") is None:
                fs = obj["floorSize"]
                if isinstance(fs, dict):
                    val = fs.get("value")
                    if val is not None:
                        try:
                            out["size_m2"] = int(float(val))
                        except (TypeError, ValueError):
                            pass
            addr = obj.get("address")
            if isinstance(addr, dict) and not out.get("location"):
                parts = [
                    str(addr.get("streetAddress") or "").strip(),
                    str(addr.get("postalCode") or "").strip(),
                    str(addr.get("addressLocality") or "").strip(),
                ]
                loc = ", ".join(p for p in parts if p)
                if loc:
                    out["location"] = loc
    return out


def parse_posted_date(text: str) -> date | None:
    return _parse_relative_posted(text)


def parse_structured_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    fields = parse_json_ld(soup)
    if fields.get("rent_eur") is None:
        fields["rent_eur"] = extract_rent_eur(text)
    if fields.get("size_m2") is None:
        fields["size_m2"] = extract_size_m2(text)
    if not fields.get("location"):
        fields["location"] = extract_location_hint(text)
    if not fields.get("platform_listed_date"):
        rel = _parse_relative_posted(text)
        if rel:
            fields["platform_listed_date"] = rel.isoformat()
    return fields
