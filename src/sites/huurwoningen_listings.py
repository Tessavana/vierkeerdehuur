"""Huurwoningen.com: discover listings via Playwright (CSR), detail pages via requests."""

from __future__ import annotations

import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from src.models import Listing
from src.web_fetch import HEADERS

# Listing URLs look like /huren/{city}/{8-char-id}/{slug}/ (hex id).
LISTING_CITIES = ("eindhoven", "veldhoven")
LISTING_PATH_RE = re.compile(
    r"^/huren/(?P<city>eindhoven|veldhoven)/(?P<id>[0-9a-f]{8})/(?P<slug>[^/?#]+)/?$",
    re.I,
)


def _to_com_base(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = parsed.path or "/in/eindhoven/"
    if "huurwoningen.nl" in host:
        host = "huurwoningen.com"
    if not host:
        host = "huurwoningen.com"
    return f"https://www.{host}{path if path.endswith('/') else path + '/'}"


def _accept_cookies(page) -> None:
    for sel in ("button#onetrust-accept-btn-handler", "button:has-text('Accepteren')"):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click(timeout=4000)
                return
        except Exception:
            continue


def _city_from_list_url(list_base_url: str) -> str:
    m = re.search(r"/in/(eindhoven|veldhoven)/?", list_base_url, re.I)
    return m.group(1).lower() if m else "eindhoven"


def _is_woningruil(path_or_url: str) -> bool:
    lower = (path_or_url or "").lower()
    return "woningruil" in lower or "huisruil" in lower or "/ruil/" in lower


def _collect_listing_hrefs_from_page(page, city: str) -> list[str]:
    hrefs = page.locator("a[href*='/huren/']").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    out: list[str] = []
    for h in hrefs:
        if not h:
            continue
        path = h.split("?")[0]
        if _is_woningruil(path):
            continue
        m = LISTING_PATH_RE.match(path)
        if not m or m.group("city").lower() != city:
            continue
        out.append(path.rstrip("/") + "/")
    return out


def _listing_urls_playwright(list_base_url: str, max_pages: int = 40) -> list[str]:
    """Scroll search pages; listing links look like /huren/{city}/{id}/{slug}/."""
    city = _city_from_list_url(list_base_url)
    seen: set[str] = set()
    ordered: list[str] = []
    storage = os.getenv("PLAYWRIGHT_STORAGE_STATE_PATH", "data/playwright_state.json")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="nl-NL")
        if os.path.exists(storage):
            context.close()
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"], locale="nl-NL", storage_state=storage
            )
        page = context.new_page()

        for page_num in range(1, max_pages + 1):
            sep = "&" if "?" in list_base_url else "?"
            url = list_base_url.rstrip("/") + ("" if page_num == 1 else f"{sep}page={page_num}")
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            _accept_cookies(page)
            try:
                page.wait_for_selector(f"a[href*='/huren/{city}/']", timeout=45000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
            for _ in range(24):
                try:
                    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                except Exception:
                    break
                page.wait_for_timeout(500)
            try:
                page.wait_for_load_state("networkidle", timeout=45000)
            except Exception:
                pass
            batch = _collect_listing_hrefs_from_page(page, city)
            new = [h for h in batch if h not in seen]
            if not batch and page_num == 1:
                break
            if not new and page_num > 1:
                break
            for h in new:
                seen.add(h)
                ordered.append(h)

        context.close()
        browser.close()

    return [urljoin("https://www.huurwoningen.com", p) for p in ordered]


def _detail_page_inactive(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    markers = (
        "niet meer beschikbaar",
        "niet langer beschikbaar",
        "deze advertentie is verwijderd",
        "advertentie niet gevonden",
        "woning is verhuurd",
        "is verhuurd",
        "reeds verhuurd",
        "aanmelding gesloten",
        "inschrijving gesloten",
        "geen woning gevonden",
        "pagina niet gevonden",
    )
    return any(m in text for m in markers)


def _extract_location(title: str, meta: str, page_text: str, fallback_city: str) -> str:
    blob = f"{title} {meta} {page_text[:6000]}".lower()
    for city in ("waalre", "veldhoven", "geldrop", "best", "nuenen", "eindhoven"):
        if re.search(rf"\b{re.escape(city)}\b", blob):
            return city.capitalize() if city != "eindhoven" else "Eindhoven"
    m = re.search(r"\b(\d{4}\s*[A-Z]{2})\b", f"{title} {page_text[:4000]}")
    if m:
        return m.group(1).upper()
    return fallback_city.capitalize() if fallback_city else "Eindhoven"


def _parse_detail(
    html: str, page_url: str, fallback_city: str = "eindhoven"
) -> tuple[str, int | None, int | None, str | None, str | None, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    meta = soup.find("meta", attrs={"name": "description"})
    meta_content = (meta.get("content", "").strip() if meta else "")[:2000]
    page_text = soup.get_text(" ", strip=True)
    blob = f"{title} {meta_content}"
    rent = None
    clean = blob.replace("\xa0", " ").replace("\u20ac", "€")
    m_rent = re.search(r"(?:€\s*|EUR\s*)(\d[\d\.]*)", clean, re.I)
    if not m_rent:
        m_rent = re.search(r"huur\s*p/?m\s*(\d[\d\.]*)", clean, re.I)
    if m_rent:
        digits = re.sub(r"[^\d]", "", m_rent.group(1))
        if digits:
            rent = int(digits)
    size = None
    m_sz = re.search(r"(\d{2,3})\s*m\s*[²2]", blob, re.I)
    if not m_sz:
        m_sz = re.search(r"(\d{2,3})\s*m\s*[²2]", page_text[:8000], re.I)
    if m_sz:
        size = int(m_sz.group(1))
    avail = None
    m_av = re.search(
        r"(?:beschikbaar|ingangsdatum|vanaf)\s*(?:per\s*)?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        page_text,
        re.I,
    )
    if m_av:
        avail = m_av.group(1).replace("/", "-")
    if not title:
        og = soup.find("meta", property="og:title")
        title = og.get("content", "").strip() if og else page_url.rstrip("/").rsplit("/", 2)[-2]
    location = _extract_location(title, meta_content, page_text, fallback_city)
    notes = meta_content[:800].strip() if meta_content else None
    return title, rent, size, avail, notes, location


def _outdoor(blob: str) -> bool:
    lowered = blob.lower()
    return any(k in lowered for k in ("balkon", "tuin", "terras", "dakterras"))


def fetch_huurwoningen_eindhoven_listings(
    list_url: str,
    max_pages: int | None = None,
    max_details: int | None = None,
) -> list[Listing]:
    if max_pages is None:
        max_pages = int(os.getenv("HUURWONINGEN_MAX_PAGES", "16"))
    if max_details is None:
        max_details = int(os.getenv("HUURWONINGEN_MAX_DETAILS", "280"))
    base = _to_com_base(list_url)
    city = _city_from_list_url(base)
    urls = _listing_urls_playwright(base, max_pages=max_pages)[: max(1, max_details)]
    session = requests.Session()
    session.headers.update(HEADERS)
    listings: list[Listing] = []
    for rel in urls:
        try:
            if _is_woningruil(rel):
                continue
            r = session.get(rel, timeout=25)
            if r.status_code >= 400:
                continue
            if _detail_page_inactive(r.text):
                continue
            title, rent, size, avail, notes, location = _parse_detail(r.text, rel, fallback_city=city)
            if _is_woningruil(f"{title} {notes or ''} {r.text[:4000]}"):
                continue
            path = urlparse(rel).path.strip("/")
            source_id = path.replace("/", "_") if path else rel
            listings.append(
                Listing(
                    source="huurwoningen",
                    source_id=source_id,
                    title=title or rel,
                    url=rel,
                    location=location,
                    rent_eur=rent,
                    size_m2=size,
                    outdoor_space=_outdoor(title + " " + (r.text[:8000] or "")),
                    available_from=avail,
                    notes=notes,
                )
            )
        except requests.RequestException:
            continue

    dedup: dict[str, Listing] = {}
    for item in listings:
        dedup[item.url] = item
    return list(dedup.values())


if __name__ == "__main__":
    import sys

    u = sys.argv[1] if len(sys.argv) > 1 else "https://www.huurwoningen.com/in/eindhoven/"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else 80
    found = fetch_huurwoningen_eindhoven_listings(u, max_pages=n, max_details=cap)
    print(f"{len(found)} listing(s) from {u} (max_pages={n})")
    for it in found[:20]:
        print(f"  EUR {it.rent_eur} | {it.size_m2} m2 | {it.available_from or '-'} | {it.title[:70]}")
