import json
import os
import re
from dataclasses import dataclass
from typing import Callable

from bs4 import BeautifulSoup

from src.filters import is_rental_match, score_rental
from src.models import Listing
from src.web_fetch import fetch_html_with_fallback


@dataclass(frozen=True)
class Platform:
    name: str
    url: str
    parser: Callable[[str, str], list[Listing]]


def _extract_int(text: str) -> int | None:
    match = re.search(r"(\d[\d\.,]*)", text)
    if not match:
        return None
    normalized = re.sub(r"[^\d]", "", match.group(1))
    return int(normalized) if normalized else None


def _has_outdoor_keywords(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in ("balcony", "garden", "terrace", "balkon", "tuin", "dakterras"))


def parse_pararius(html: str, page_url: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("section.listing-search-item")
    listings: list[Listing] = []
    for card in cards:
        link = card.select_one("a.listing-search-item__link--title")
        if not link or not link.get("href"):
            continue
        title = link.get_text(" ", strip=True)
        location_el = card.select_one("div.listing-search-item__location")
        price_el = card.select_one("div.listing-search-item__price")
        area_el = card.select_one("li.illustrated-features__item--surface-area")
        location = location_el.get_text(" ", strip=True) if location_el else ""
        listings.append(
            Listing(
                source="pararius",
                source_id=link["href"].strip("/"),
                title=title,
                url="https://www.pararius.com" + link["href"],
                location=location,
                rent_eur=_extract_int(price_el.get_text(" ", strip=True)) if price_el else None,
                size_m2=_extract_int(area_el.get_text(" ", strip=True)) if area_el else None,
                outdoor_space=_has_outdoor_keywords(title + " " + location),
                contract_months=None,
            )
        )
    return listings


def parse_funda(html: str, page_url: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
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
            offers = obj.get("offers", {})
            name = str(obj.get("name", "Funda listing"))
            item_url = str(obj.get("url", page_url))
            location_text = str(obj.get("areaServed", "Eindhoven"))
            listings.append(
                Listing(
                    source="funda",
                    source_id=item_url.rstrip("/").split("/")[-1],
                    title=name,
                    url=item_url if item_url.startswith("http") else f"https://www.funda.nl{item_url}",
                    location=location_text,
                    rent_eur=_extract_int(str(offers.get("price", ""))),
                    size_m2=_extract_int(name),
                    outdoor_space=_has_outdoor_keywords(name),
                    contract_months=None,
                )
            )
    return listings


def parse_huurwoningen(html: str, page_url: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    for a in soup.select("a[href*='/huurwoning/']"):
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        listings.append(
            Listing(
                source="huurwoningen",
                source_id=href.strip("/"),
                title=title,
                url=href if href.startswith("http") else f"https://www.huurwoningen.nl{href}",
                location="Eindhoven",
                rent_eur=_extract_int(title),
                size_m2=None,
                outdoor_space=_has_outdoor_keywords(title),
                contract_months=None,
            )
        )
    return listings


def parse_kamernet(html: str, page_url: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
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


def parse_directwonen(html: str, page_url: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    for a in soup.select("a[href*='/huurwoning/']"):
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        listings.append(
            Listing(
                source="directwonen",
                source_id=href.strip("/"),
                title=title,
                url=href if href.startswith("http") else f"https://directwonen.nl{href}",
                location="Eindhoven",
                rent_eur=_extract_int(title),
                size_m2=None,
                outdoor_space=_has_outdoor_keywords(title),
                contract_months=None,
            )
        )
    return listings


def parse_noop(html: str, page_url: str) -> list[Listing]:
    return []


PLATFORMS = [
    Platform("Pararius", "https://www.pararius.com/apartments/eindhoven", parse_pararius),
    Platform("Funda", "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D", parse_funda),
    Platform("Huurwoningen", "https://www.huurwoningen.nl/in/eindhoven/", parse_huurwoningen),
    Platform("Kamernet", "https://kamernet.nl/en/for-rent/apartment-eindhoven", parse_kamernet),
    Platform("DirectWonen", "https://directwonen.nl/huurwoningen-huren/eindhoven", parse_directwonen),
    Platform("Huislijn", "https://www.huislijn.nl/huurwoningen/nederland/noord-brabant/eindhoven", parse_noop),
    Platform("Vesteda", "https://www.vesteda.com/nl/huurwoningen-eindhoven", parse_noop),
]


class ProbeConfig:
    max_rent = 1150
    min_size = 20


def _anti_bot_hint(html: str) -> str | None:
    text = html[:1200].lower()
    hints = ("just a moment", "cloudflare", "captcha", "access denied", "bot", "je bent bijna")
    for hint in hints:
        if hint in text:
            return hint
    return None


def run_probe() -> None:
    env_urls = [u.strip() for u in os.getenv("PROBE_URLS", "").split(",") if u.strip()]
    platforms = _platforms_from_urls(env_urls) if env_urls else PLATFORMS
    print("=== Eindhoven Rental Platform Probe ===")
    for platform in platforms:
        print(f"\n[{platform.name}] {platform.url}")
        try:
            fetched = fetch_html_with_fallback(platform.url)
            print(f"status=ok browser_fallback={'yes' if fetched.used_browser else 'no'}")
        except Exception as exc:
            print(f"request_error={exc}")
            continue

        anti_bot = _anti_bot_hint(fetched.html)
        if anti_bot:
            print(f"reliability=BLOCKED ({anti_bot})")
            continue

        listings = platform.parser(fetched.html, fetched.final_url)
        suitable = [l for l in listings if is_rental_match(l, ProbeConfig)]
        print(f"reliability={'RELIABLE' if listings else 'PARTIAL'} parsed={len(listings)} suitable={len(suitable)}")
        for listing in suitable[:5]:
            score = score_rental(listing, ProbeConfig)
            print(
                f"- score={score} rent={listing.rent_eur} size={listing.size_m2} "
                f"title={listing.title[:72]} url={listing.url}"
            )
        if not suitable:
            print("- no suitable listings detected with current parser/filters")


def _platforms_from_urls(urls: list[str]) -> list[Platform]:
    platforms: list[Platform] = []
    for url in urls:
        lower = url.lower()
        if "pararius.com" in lower:
            platforms.append(Platform("Pararius", url, parse_pararius))
        elif "funda.nl" in lower:
            platforms.append(Platform("Funda", url, parse_funda))
        elif "huurwoningen.nl" in lower:
            platforms.append(Platform("Huurwoningen", url, parse_huurwoningen))
        elif "kamernet.nl" in lower:
            platforms.append(Platform("Kamernet", url, parse_kamernet))
        elif "directwonen.nl" in lower:
            platforms.append(Platform("DirectWonen", url, parse_directwonen))
        elif "huislijn.nl" in lower:
            platforms.append(Platform("Huislijn", url, parse_noop))
        elif "vesteda.com" in lower:
            platforms.append(Platform("Vesteda", url, parse_noop))
        else:
            platforms.append(Platform("Unknown", url, parse_noop))
    return platforms


if __name__ == "__main__":
    run_probe()
