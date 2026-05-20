import xml.etree.ElementTree as ET
from io import BytesIO

import requests

r = requests.get("https://vbth.eye-move.nl/export/Woningen.xml", timeout=120, headers={"User-Agent": "Mozilla/5.0"})
for _ev, elem in ET.iterparse(BytesIO(r.content), events=("end",)):
    if elem.tag != "Woning":
        continue
    if "eindhoven" not in (elem.findtext("Adres/Plaats") or "").lower():
        elem.clear()
        continue
    if (elem.findtext("prijzen/KoopHuur") or "").lower() not in ("", "huur"):
        if (elem.findtext("prijzen/KoopHuur") or "").lower() != "huur":
            elem.clear()
            continue

    def walk(el, prefix=""):
        for child in el:
            walk(child, f"{prefix}/{child.tag}" if prefix else child.tag)
            if child.text and child.text.strip() and len(child) == 0:
                print(f"{prefix}/{child.tag}: {child.text.strip()[:80]}")

    walk(elem)
    break
