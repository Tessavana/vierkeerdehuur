"""Fetch housing-related posts from Reddit via public RSS (no API key)."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from src.seekers.common import SeekerPost, post_from_fields, strip_html

_ATOM = {"a": "http://www.w3.org/2005/Atom"}
_USER_AGENT = "vierkeerdehuur/1.0 (eindhoven housing seeker feed)"


def _fetch_rss(url: str) -> list[dict]:
    try:
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=25)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError):
        return []

    rows: list[dict] = []
    for entry in root.findall("a:entry", _ATOM):
        title_el = entry.find("a:title", _ATOM)
        link_el = entry.find("a:link", _ATOM)
        updated_el = entry.find("a:updated", _ATOM)
        content_el = entry.find("a:content", _ATOM)
        author_el = entry.find("a:author/a:name", _ATOM)
        if title_el is None or link_el is None:
            continue
        link = link_el.get("href") or ""
        post_id = link.rstrip("/").split("/")[-1] or link
        updated = updated_el.text if updated_el is not None else None
        rows.append(
            {
                "id": f"reddit-{post_id}",
                "title": title_el.text or "",
                "url": link,
                "snippet": strip_html(content_el.text if content_el is not None else ""),
                "posted_at": updated,
                "author": author_el.text if author_el is not None else "",
                "group_name": _subreddit_from_url(url),
            }
        )
    return rows


def _subreddit_from_url(rss_url: str) -> str:
    m = re.search(r"/r/([^/]+)/", rss_url)
    return f"r/{m.group(1)}" if m else "Reddit"


def fetch_reddit_seekers() -> list[SeekerPost]:
    feeds = os.getenv(
        "REDDIT_SEEKER_RSS",
        "https://www.reddit.com/r/eindhoven/new.rss",
    ).split(",")
    out: list[SeekerPost] = []
    seen: set[str] = set()
    for raw in feeds:
        url = raw.strip()
        if not url:
            continue
        for row in _fetch_rss(url):
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            post = post_from_fields(source="reddit", **row)
            if post:
                out.append(post)
    out.sort(key=lambda p: p.posted_at or "", reverse=True)
    return out[: int(os.getenv("REDDIT_SEEKER_MAX", "25"))]
