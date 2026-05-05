import re
import json
from abc import ABC, abstractmethod
from pathlib import Path

from bs4 import BeautifulSoup

from src.models import Listing
from src.web_fetch import fetch_html_with_fallback


class ListingProvider(ABC):
    @abstractmethod
    def fetch(self) -> list[Listing]:
        raise NotImplementedError


class ParariusProvider(ListingProvider):
    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> list[Listing]:
        fetched = fetch_html_with_fallback(self.url)
        soup = BeautifulSoup(fetched.html, "html.parser")
        cards = soup.select("section.listing-search-item")
        listings: list[Listing] = []
        for card in cards:
            link = card.select_one("a.listing-search-item__link--title")
            if not link or not link.get("href"):
                continue
            url = "https://www.pararius.com" + link["href"]
            source_id = link["href"].strip("/")
            title = link.get_text(" ", strip=True)
            location_el = card.select_one("div.listing-search-item__location")
            location = location_el.get_text(" ", strip=True) if location_el else ""
            price_el = card.select_one("div.listing-search-item__price")
            area_el = card.select_one("li.illustrated-features__item--surface-area")
            rent_eur = _extract_int(price_el.get_text(" ", strip=True)) if price_el else None
            size_m2 = _extract_int(area_el.get_text(" ", strip=True)) if area_el else None
            listings.append(
                Listing(
                    source="pararius",
                    source_id=source_id,
                    title=title,
                    url=url,
                    location=location,
                    rent_eur=rent_eur,
                    size_m2=size_m2,
                    outdoor_space=_has_outdoor_keywords(title + " " + location),
                    contract_months=None,
                )
            )
        return listings


class KamernetProvider(ListingProvider):
    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> list[Listing]:
        fetched = fetch_html_with_fallback(self.url)
        soup = BeautifulSoup(fetched.html, "html.parser")
        listings: list[Listing] = []
        for card in soup.select("a[href*='/en/for-rent/']"):
            href = card.get("href", "")
            title = card.get_text(" ", strip=True)
            if not href or len(title) < 10:
                continue
            if href.rstrip("/") in ("/en/for-rent/apartment-eindhoven", "/en/for-rent/apartment-helmond"):
                continue
            rent_match = re.search(r"[€\u20ac]\s?(\d[\d\.,]*)", title)
            size_match = re.search(r"(\d{2,3})\s?m", title.lower())
            city_match = re.search(r",\s*([A-Za-z\u00c0-\u017f' -]+)\s+\d{2,3}\s?m", title)
            rent = _extract_int(rent_match.group(1)) if rent_match else None
            size = _extract_int(size_match.group(1)) if size_match else None
            location = city_match.group(1).strip() if city_match else "Unknown"
            listings.append(
                Listing(
                    source="kamernet",
                    source_id=href.strip("/"),
                    title=title,
                    url=href if href.startswith("http") else f"https://kamernet.nl{href}",
                    location=location,
                    rent_eur=rent,
                    size_m2=size,
                    outdoor_space=_has_outdoor_keywords(title),
                    contract_months=None,
                )
            )
        return listings


class FundaProvider(ListingProvider):
    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> list[Listing]:
        fetched = fetch_html_with_fallback(self.url)
        soup = BeautifulSoup(fetched.html, "html.parser")
        listings: list[Listing] = []
        for script in soup.select('script[type="application/ld+json"]'):
            text = script.string or script.get_text(strip=True)
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            objects = payload if isinstance(payload, list) else [payload]
            for obj in objects:
                if obj.get("@type") != "Product":
                    continue
                name = str(obj.get("name", "Funda listing"))
                item_url = str(obj.get("url", self.url))
                offers = obj.get("offers", {}) if isinstance(obj.get("offers"), dict) else {}
                listings.append(
                    Listing(
                        source="funda",
                        source_id=item_url.rstrip("/").split("/")[-1],
                        title=name,
                        url=item_url if item_url.startswith("http") else f"https://www.funda.nl{item_url}",
                        location="Eindhoven",
                        rent_eur=_extract_int(str(offers.get("price", ""))),
                        size_m2=_extract_int(name),
                        outdoor_space=_has_outdoor_keywords(name),
                        contract_months=None,
                    )
                )
        return listings


class VbtProvider(ListingProvider):
    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> list[Listing]:
        fetched = fetch_html_with_fallback(self.url)
        soup = BeautifulSoup(fetched.html, "html.parser")
        listings: list[Listing] = []
        for link in soup.select("a[href*='huur'], a[href*='woning']"):
            href = link.get("href", "")
            title = link.get_text(" ", strip=True)
            if not href or len(title) < 8:
                continue
            listings.append(
                Listing(
                    source="vbt",
                    source_id=href.strip("/"),
                    title=title,
                    url=href if href.startswith("http") else f"https://vbtverhuurmakelaars.nl{href}",
                    location="Eindhoven",
                    rent_eur=_extract_int(title),
                    size_m2=_extract_int(title),
                    outdoor_space=_has_outdoor_keywords(title),
                    contract_months=None,
                )
            )
        return _dedupe_listings(listings)


class VestedaProvider(ListingProvider):
    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> list[Listing]:
        fetched = fetch_html_with_fallback(self.url)
        soup = BeautifulSoup(fetched.html, "html.parser")
        listings: list[Listing] = []
        for link in soup.select("a[href*='huurwoning'], a[href*='rent']"):
            href = link.get("href", "")
            title = link.get_text(" ", strip=True)
            if not href or len(title) < 8:
                continue
            listings.append(
                Listing(
                    source="vesteda",
                    source_id=href.strip("/"),
                    title=title,
                    url=href if href.startswith("http") else f"https://www.vesteda.com{href}",
                    location="Eindhoven",
                    rent_eur=_extract_int(title),
                    size_m2=_extract_int(title),
                    outdoor_space=_has_outdoor_keywords(title),
                    contract_months=None,
                )
            )
        return _dedupe_listings(listings)


class JsonFileProvider(ListingProvider):
    def __init__(self, path: Path) -> None:
        self.path = path

    def fetch(self) -> list[Listing]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        listings: list[Listing] = []
        for item in payload:
            listings.append(
                Listing(
                    source=item.get("source", "sample"),
                    source_id=item["source_id"],
                    title=item["title"],
                    url=item["url"],
                    location=item["location"],
                    rent_eur=item.get("rent_eur"),
                    size_m2=item.get("size_m2"),
                    outdoor_space=bool(item.get("outdoor_space", False)),
                    contract_months=item.get("contract_months"),
                )
            )
        return listings


def _extract_int(text: str) -> int | None:
    match = re.search(r"(\d[\d\.,]*)", text)
    if not match:
        return None
    normalized = re.sub(r"[^\d]", "", match.group(1))
    return int(normalized) if normalized else None


def _has_outdoor_keywords(text: str) -> bool:
    lowered = text.lower()
    keywords = ("balcony", "garden", "terrace", "balkon", "tuin", "dakterras")
    return any(k in lowered for k in keywords)


def _dedupe_listings(listings: list[Listing]) -> list[Listing]:
    deduped: list[Listing] = []
    seen: set[str] = set()
    for listing in listings:
        if listing.source_id in seen:
            continue
        seen.add(listing.source_id)
        deduped.append(listing)
    return deduped
