import json
import re

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# From __NUXT__ on search page
base = "https://listing-search-wonen.funda.nl"

endpoints = [
    f"{base}/search?selected_area=eindhoven&offering_type=rent",
    f"{base}/listings?city=eindhoven",
    "https://listing-search-wonen.funda.nl/_msearch",
]

for url in endpoints:
    try:
        r = requests.get(url, headers=H, timeout=20)
        print(url, r.status_code, r.headers.get("content-type"), r.text[:300])
    except Exception as e:
        print(url, e)

# Try elasticsearch style from page scripts
r = requests.get(
    "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D",
    headers=H,
    timeout=30,
)
for m in re.finditer(r'"globalId"\s*:\s*"?(\d+)"?', r.text):
    print("globalId", m.group(1))
    break
ids = re.findall(r"/detail/huur/eindhoven/[^\"']+/(\d+)/", r.text)
print("detail ids in static html", len(set(ids)), list(set(ids))[:5])
