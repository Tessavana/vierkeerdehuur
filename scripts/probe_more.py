import json
import xml.etree.ElementTree as ET
from io import BytesIO

import requests

H = {"User-Agent": "Mozilla/5.0"}


def vbt_price_fields() -> None:
    r = requests.get("https://vbth.eye-move.nl/export/Woningen.xml", timeout=120, headers=H)
    for _ev, elem in ET.iterparse(BytesIO(r.content), events=("end",)):
        if elem.tag != "Woning":
            continue
        plaats = elem.findtext("Adres/Plaats") or ""
        if "eindhoven" not in plaats.lower():
            elem.clear()
            continue
        prijzen = elem.find("prijzen")
        if prijzen is not None:
            for child in prijzen:
                print("prijzen/", child.tag, child.text)
        ken = elem.find("Kenmerken")
        if ken is not None:
            for child in list(ken)[:15]:
                print("ken/", child.tag, (child.text or "")[:40])
        elem.clear()
        break


def rotsvast_api() -> None:
    for path in ("/api", "/api/properties", "/api/v1/properties", "/api/woningen"):
        url = f"https://www.rotsvast.nl{path}"
        r = requests.get(url, headers=H, timeout=20)
        print(path, r.status_code, r.headers.get("content-type"), r.text[:500])


def funda_pagination() -> None:
    from bs4 import BeautifulSoup

    base = "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D"
    for page in ("", "&search_result=1", "&search_result=2"):
        r = requests.get(base + page, headers=H, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        for sc in soup.find_all("script", type="application/ld+json"):
            data = json.loads(sc.string or sc.get_text())
            if isinstance(data, dict) and data.get("itemListElement"):
                print("page", page or "0", "count", len(data["itemListElement"]))
                break


if __name__ == "__main__":
    vbt_price_fields()
    rotsvast_api()
    funda_pagination()
