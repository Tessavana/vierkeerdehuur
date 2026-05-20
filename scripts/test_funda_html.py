import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re

from src.web_fetch import fetch_html_with_playwright

url = "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D"
f = fetch_html_with_playwright(url, wait_ms=12000)
html = f.html
print("len", len(html))
for pat in (
    r"/detail/huur/eindhoven/",
    r"detail/huur",
    r"globalId",
    r"itemListElement",
    r"zoekresultaten",
):
    print(pat, pat in html if isinstance(pat, str) else "", html.count(pat) if isinstance(pat, str) else "")
print("sample detail", re.findall(r"/detail/huur/eindhoven/[a-z0-9-]+/\d+", html)[:5])
print("cassandra", "cassandraplein" in html.lower())
