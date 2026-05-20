import json
import re

import requests

H = {"User-Agent": "Mozilla/5.0"}
r = requests.get("https://www.rotsvast.nl/wp-json/", headers=H, timeout=20)
data = r.json()
routes = data.get("routes", {})
for key in sorted(routes):
    if "sumedia" in key.lower() or "woning" in key.lower() or "property" in key.lower() or "sure" in key.lower():
        print(key, routes[key].get("methods"))

# grep HTML
html = requests.get("https://www.rotsvast.nl/woningaanbod/huur/eindhoven/", headers=H, timeout=30).text
for m in re.finditer(r"sumedia/v1[^\s\"']*", html):
    print("html route", m.group(0)[:80])
