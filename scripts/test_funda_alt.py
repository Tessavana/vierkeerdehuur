import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import re

import requests
from bs4 import BeautifulSoup

from src.sites.funda_huur import _urls_from_search_html
from src.web_fetch import HEADERS, fetch_html_with_playwright

urls = [
    "https://www.funda.nl/huur/eindhoven/",
    "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D",
]
for url in urls:
    r = requests.get(url, headers=HEADERS, timeout=30)
    print("\n", url, "len", len(r.text))
    print("urls from parser", len(_urls_from_search_html(r.text)))
    try:
        f = fetch_html_with_playwright(url, wait_ms=10000)
        print("pw len", len(f.html), "urls", len(_urls_from_search_html(f.html)))
    except Exception as e:
        print("pw err", e)
