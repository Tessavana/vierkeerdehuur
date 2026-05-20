import json
import re
import xml.etree.ElementTree as ET
from io import BytesIO

import requests
from bs4 import BeautifulSoup

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def probe_rotsvast() -> None:
    print("\n--- rotsvast ---")
    for path in ("/wp-json/", "/wp-json/wp/v2/"):
        url = f"https://www.rotsvast.nl{path}"
        r = requests.get(url, headers=H, timeout=20)
        print(path, r.status_code, r.text[:300])
    r = requests.get("https://www.rotsvast.nl/woningaanbod/huur/eindhoven/", headers=H, timeout=30)
    apis = set(re.findall(r"https?://[^\s\"']+", r.text))
    for a in sorted(apis):
        if "api" in a.lower() or "sure" in a.lower():
            print("url", a[:140])


def probe_funda() -> None:
    print("\n--- funda ---")
    r = requests.get(
        "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D",
        headers=H,
        timeout=30,
    )
    soup = BeautifulSoup(r.text, "html.parser")
    for sc in soup.find_all("script", type="application/ld+json"):
        data = json.loads(sc.string or sc.get_text())
        if isinstance(data, dict) and data.get("itemListElement"):
            els = data["itemListElement"]
            print("count", len(els))
            u = els[0].get("url", "")
            print("first", u)
            dr = requests.get(u, headers=H, timeout=20)
            dsoup = BeautifulSoup(dr.text, "html.parser")
            for sc2 in dsoup.find_all("script", type="application/ld+json"):
                d2 = json.loads(sc2.string or sc2.get_text())
                objs = d2 if isinstance(d2, list) else [d2]
                for o in objs:
                    if not isinstance(o, dict):
                        continue
                    if o.get("offers") or o.get("@type") in (
                        "Product",
                        "Apartment",
                        "House",
                        "Residence",
                        "SingleFamilyResidence",
                    ):
                        print("detail type", o.get("@type"), "name", o.get("name"))
                        print("  offers", o.get("offers"))
                        print("  address", o.get("address"))
            break


def probe_vbt_woning() -> None:
    print("\n--- vbt woning xml ---")
    r = requests.get("https://vbth.eye-move.nl/export/Woningen.xml", timeout=120, headers=H)
    for _ev, elem in ET.iterparse(BytesIO(r.content), events=("end",)):
        if elem.tag != "Woning":
            continue
        plaats = elem.findtext("Adres/Plaats") or ""
        if "eindhoven" not in plaats.lower():
            elem.clear()
            continue
        for path in (
            "DeeplinkUrl",
            "prijzen/Huurprijs",
            "prijzen/HuurprijsVan",
            "Kenmerken/Woonoppervlakte",
            "Kenmerken/Woonoppervlak",
            "Status",
            "Archief",
            "Internet",
            "Adres/Straat",
            "Adres/Huisnummer",
            "Adres/Postcode",
        ):
            print(path, elem.findtext(path))
        elem.clear()
        break


def probe_nmg() -> None:
    print("\n--- nmg ---")
    r = requests.get("https://nmgwonen.nl/huurwoningen/eindhoven/", headers=H, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.select("a"):
        href = a.get("href") or ""
        if "/woning/" in href:
            print(href, a.get_text(" ", strip=True)[:80])


if __name__ == "__main__":
    probe_rotsvast()
    probe_funda()
    probe_vbt_woning()
    probe_nmg()
