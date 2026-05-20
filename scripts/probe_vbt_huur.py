import xml.etree.ElementTree as ET
from io import BytesIO

import requests

H = {"User-Agent": "Mozilla/5.0"}
r = requests.get("https://vbth.eye-move.nl/export/Woningen.xml", timeout=120, headers=H)
shown = 0
for _ev, elem in ET.iterparse(BytesIO(r.content), events=("end",)):
    if elem.tag != "Woning":
        continue
    plaats = elem.findtext("Adres/Plaats") or ""
    if "eindhoven" not in plaats.lower():
        elem.clear()
        continue
    koop_huur = (elem.findtext("prijzen/KoopHuur") or "").strip().lower()
    if koop_huur and koop_huur != "huur":
        elem.clear()
        continue
    archief = (elem.findtext("Archief") or "").lower()
    if archief == "ja":
        elem.clear()
        continue
    print("---", elem.findtext("DeeplinkUrl"))
    prijzen = elem.find("prijzen")
    if prijzen is not None:
        for child in prijzen:
            print(" ", child.tag, child.text)
    print(" status", elem.findtext("Status"), "internet", elem.findtext("Internet"))
    print(" size", elem.findtext("Kenmerken/GebruiksoppervlakteWoonfunctie"))
    shown += 1
    elem.clear()
    if shown >= 5:
        break
print("shown", shown)
