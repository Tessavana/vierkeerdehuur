import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sites.funda_huur import _urls_from_search_html
from src.web_fetch import HEADERS, fetch_html_with_fallback
import requests
from bs4 import BeautifulSoup
import json

url = "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D"
r = requests.get(url, headers=HEADERS, timeout=30)
print("requests len", len(r.text))
print("parse urls", len(_urls_from_search_html(r.text)))
f = fetch_html_with_fallback(url)
print("fallback browser", f.used_browser, "urls", len(_urls_from_search_html(f.html)))
