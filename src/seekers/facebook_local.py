"""Facebook groups — local Playwright only. Writes cache for workrun to merge."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from src.seekers.common import SeekerPost, post_from_fields, strip_html

_CACHE = Path(os.getenv("FACEBOOK_SEEKERS_CACHE", "data/facebook_seekers_cache.json"))
_DEFAULT_GROUPS = (
    "https://www.facebook.com/groups/woninghureneindhoven",
    "https://www.facebook.com/groups/eindhoventehuur",
)


def _load_cache() -> list[dict]:
    if not _CACHE.exists():
        return []
    try:
        raw = json.loads(_CACHE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else raw.get("posts", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save_cache(posts: list[SeekerPost]) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "posts": [p.to_dict() for p in posts],
    }
    _CACHE.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def load_facebook_seekers_from_cache() -> list[SeekerPost]:
    rows = _load_cache()
    out: list[SeekerPost] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            out.append(SeekerPost(**{k: row[k] for k in SeekerPost.__dataclass_fields__ if k in row}))
        except (TypeError, KeyError):
            continue
    return out


def fetch_facebook_groups_local() -> list[SeekerPost]:
    """Run on your machine with logged-in Facebook session. Not for CI."""
    if os.getenv("FACEBOOK_SEEKERS_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return load_facebook_seekers_from_cache()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return load_facebook_seekers_from_cache()

    storage = os.getenv("PLAYWRIGHT_STORAGE_STATE_PATH", "data/playwright_state.json")
    if not Path(storage).exists():
        print("facebook seekers: no playwright session — run session_bootstrap with Facebook first")
        return load_facebook_seekers_from_cache()

    group_urls = [
        u.strip()
        for u in os.getenv("FACEBOOK_GROUP_URLS", ",".join(_DEFAULT_GROUPS)).split(",")
        if u.strip()
    ]
    max_posts = int(os.getenv("FACEBOOK_SEEKER_MAX", "30"))
    out: list[SeekerPost] = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=storage,
            locale="nl-NL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = context.new_page()
        for group_url in group_urls:
            try:
                page.goto(group_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(4000)
                for _ in range(6):
                    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                    page.wait_for_timeout(800)
                html = page.content()
            except Exception as exc:
                print(f"facebook seekers: skip {group_url}: {exc}")
                continue

            group_name = _group_name_from_html(html) or group_url.rstrip("/").split("/")[-1]
            for block in _extract_post_blocks(html):
                if block["url"] in seen:
                    continue
                seen.add(block["url"])
                post = post_from_fields(
                    source="facebook",
                    group_name=group_name,
                    **block,
                )
                if post and post.kind in {"seeking", "unknown"}:
                    out.append(post)
                if len(out) >= max_posts:
                    break
            if len(out) >= max_posts:
                break
            time.sleep(1.5)
        context.close()
        browser.close()

    out.sort(key=lambda p: p.posted_at or "", reverse=True)
    _save_cache(out)
    return out


def _group_name_from_html(html: str) -> str:
    m = re.search(r'"group_name":"([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r"<title>([^<|]+)", html)
    return m.group(1).strip() if m else ""


def _extract_post_blocks(html: str) -> list[dict]:
    """Best-effort parse of visible post links in group feed HTML."""
    blocks: list[dict] = []
    for m in re.finditer(r'href="(https://www\.facebook\.com/groups/\d+/posts/\d+[^"]*)"', html):
        url = m.group(1).split("?")[0]
        pid = url.rstrip("/").split("/")[-1]
        start = max(0, m.start() - 400)
        chunk = html[start : m.start() + 200]
        text = strip_html(chunk)
        if len(text) < 20:
            continue
        blocks.append(
            {
                "id": f"facebook-{pid}",
                "title": text[:200],
                "snippet": text[:500],
                "url": url,
                "posted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    dedup: dict[str, dict] = {}
    for b in blocks:
        dedup[b["url"]] = b
    return list(dedup.values())


if __name__ == "__main__":
    posts = fetch_facebook_groups_local()
    print(f"Facebook seekers: {len(posts)} post(s) cached to {_CACHE}")
