"""Fetch housing-related posts from Reddit via public RSS (no API key)."""

from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET

import requests

from src.seekers.common import SeekerPost, classify_kind, post_from_fields, strip_html
from src.seekers.relevance import is_relevant_post, score_relevance

_ATOM = {"a": "http://www.w3.org/2005/Atom"}
_USER_AGENT = "vierkeerdehuur/1.0 (eindhoven housing seeker feed)"


def _fetch_rss(url: str) -> list[dict]:
    retries = int(os.getenv("REDDIT_SEEKER_RETRIES", "3"))
    backoff = float(os.getenv("REDDIT_SEEKER_BACKOFF", "4.0"))
    root = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=25)
            if r.status_code == 429:
                if attempt + 1 < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                print("seekers reddit: rate limited (429)")
                return []
            if r.status_code != 200:
                return []
            root = ET.fromstring(r.content)
            break
        except (requests.RequestException, ET.ParseError):
            if attempt + 1 < retries:
                time.sleep(backoff)
                continue
            return []
    if root is None:
        return []

    subreddit = _subreddit_from_url(url)
    rows: list[dict] = []
    for entry in root.findall("a:entry", _ATOM):
        title_el = entry.find("a:title", _ATOM)
        link_el = entry.find("a:link", _ATOM)
        updated_el = entry.find("a:updated", _ATOM)
        published_el = entry.find("a:published", _ATOM)
        content_el = entry.find("a:content", _ATOM)
        author_el = entry.find("a:author/a:name", _ATOM)
        if title_el is None or link_el is None:
            continue
        link = link_el.get("href") or ""
        post_id = link.rstrip("/").split("/")[-1] or link
        posted = (published_el.text if published_el is not None else None) or (
            updated_el.text if updated_el is not None else None
        )
        title = title_el.text or ""
        snippet = strip_html(content_el.text if content_el is not None else "")
        if not is_relevant_post(title, snippet, subreddit=subreddit, source="reddit"):
            continue
        rel = score_relevance(title, snippet, subreddit=subreddit)
        rows.append(
            {
                "id": f"reddit-{post_id}",
                "title": title,
                "url": link,
                "snippet": snippet,
                "posted_at": posted,
                "author": author_el.text if author_el is not None else "",
                "group_name": subreddit,
                "kind": classify_kind(title, snippet),
                "relevance_score": rel.get("score", 0),
            }
        )
    return rows


def _subreddit_from_url(rss_url: str) -> str:
    m = re.search(r"/r/([^/]+)/", rss_url)
    return f"r/{m.group(1)}" if m else "Reddit"


def fetch_reddit_seekers() -> list[SeekerPost]:
    feeds = os.getenv(
        "REDDIT_SEEKER_RSS",
        "https://www.reddit.com/r/eindhoven/new.rss,https://www.reddit.com/r/NetherlandsHousing/new.rss",
    ).split(",")
    out: list[SeekerPost] = []
    seen: set[str] = set()
    for raw in feeds:
        url = raw.strip()
        if not url:
            continue
        if len(seen) > 0:
            time.sleep(float(os.getenv("REDDIT_SEEKER_INTERVAL", "2.0")))
        for row in _fetch_rss(url):
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            post = post_from_fields(source="reddit", **row)
            if post:
                out.append(post)
    out.sort(key=lambda p: p.posted_at or "", reverse=True)
    return out[: int(os.getenv("REDDIT_SEEKER_MAX", "40"))]


def build_reddit_overview(posts: list[SeekerPost]) -> dict:
    reddit = [p for p in posts if p.source == "reddit"]
    reddit.sort(key=lambda p: p.posted_at or "", reverse=True)
    seeking = [p for p in reddit if p.kind == "seeking"]
    offering = [p for p in reddit if p.kind == "offering"]
    unknown = [p for p in reddit if p.kind == "unknown"]

    def _row(p: SeekerPost) -> dict:
        return {
            "title": p.title,
            "url": p.url,
            "posted_at": p.posted_at,
            "author": p.author,
            "budget_eur": p.budget_eur,
            "location_hint": p.location_hint,
            "kind": p.kind,
            "group_name": p.group_name,
        }

    subreddits = sorted({p.group_name for p in reddit if p.group_name})

    return {
        "subreddits": subreddits,
        "subreddit": " · ".join(subreddits) if subreddits else "Reddit",
        "total_relevant": len(reddit),
        "seeking": len(seeking),
        "offering": len(offering),
        "unknown": len(unknown),
        "recent_asks": [_row(p) for p in seeking[:10]],
        "recent_posts": [_row(p) for p in reddit[:12]],
    }
