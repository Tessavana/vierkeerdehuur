"""One-off probe for site HTML structure."""
import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

sites = [
    ("funda", "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D"),
    ("vbt", "https://vbtverhuurmakelaars.nl/huurwoningen-eindhoven"),
    ("rotsvast", "https://www.rotsvast.nl/huurwoningen/eindhoven"),
    ("nmg", "https://www.nmgwonen.nl/huurwoningen/eindhoven"),
]

for name, url in sites:
    print(f"\n=== {name} ===")
    r = requests.get(url, timeout=30, headers=HEADERS)
    print("status", r.status_code, "len", len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        t = s.string or s.get_text()
        if t and len(t) > 50:
            print("ld+json type sample:", t[:400])
            break
    # funda: look for embedded JSON
    if name == "funda":
        for s in soup.find_all("script"):
            t = s.string or ""
            if not t or len(t) < 100:
                continue
            if "zoekresultaten" in t.lower() or "searchresult" in t.lower() or "__NUXT__" in t:
                print("script snippet:", t[:500].replace("\n", " "))
    # link patterns
    patterns = []
    for a in soup.select("a[href]"):
        h = a.get("href", "")
        if name == "rotsvast" and "/huurwoningen/" in h and h.count("/") >= 4:
            patterns.append(h)
        elif name == "nmg" and "huur" in h.lower():
            patterns.append(h)
        elif name == "vbt" and "/Project/" in h:
            patterns.append(h)
        elif name == "funda" and "/detail/huur/" in h:
            patterns.append(h)
    print("matching links:", list(dict.fromkeys(patterns))[:12])
