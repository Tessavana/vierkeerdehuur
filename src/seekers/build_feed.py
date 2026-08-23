"""Build merged seekers feed for the dashboard."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.seekers.common import SeekerPost
from src.seekers.relevance import is_relevant_post
from src.seekers.facebook_local import load_facebook_seekers_from_cache
from src.seekers.marktplaats_gezocht import fetch_marktplaats_seekers
from src.seekers.reddit_rss import build_reddit_overview, fetch_reddit_seekers

_REGISTRY = Path(os.getenv("SEEKERS_REGISTRY_PATH", "data/seekers_registry.json"))
_OUTPUT = Path("docs/data/seekers_feed.json")


def _load_registry() -> dict[str, dict]:
    if not _REGISTRY.exists():
        return {}
    try:
        raw = json.loads(_REGISTRY.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_registry(registry: dict[str, dict]) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY.write_text(json.dumps(registry, indent=2, ensure_ascii=True), encoding="utf-8")


def _post_is_relevant(post: SeekerPost) -> bool:
    if post.kind == "offering":
        return False
    return is_relevant_post(
        post.title, post.snippet, subreddit=post.group_name, source=post.source
    )


def _merge_registry(posts: list[SeekerPost]) -> list[SeekerPost]:
    now = datetime.now(timezone.utc).isoformat()
    registry = _load_registry()
    for post in posts:
        key = post.url.strip().lower()
        entry = registry.get(key) or {}
        if "first_seen_utc" not in entry:
            entry["first_seen_utc"] = now
        entry["last_seen_utc"] = now
        entry.update(post.to_dict())
        registry[key] = entry

    fields = SeekerPost.__dataclass_fields__
    stale: list[str] = []
    merged: list[SeekerPost] = []
    for key, row in registry.items():
        try:
            post = SeekerPost(**{k: row[k] for k in fields if k in row})
        except (TypeError, KeyError):
            stale.append(key)
            continue
        if not _post_is_relevant(post):
            stale.append(key)
            continue
        merged.append(post)
    for key in stale:
        registry.pop(key, None)
    _save_registry(registry)
    merged.sort(key=lambda p: p.posted_at or "", reverse=True)
    return merged


def build_seekers_feed() -> dict:
    if os.getenv("SEEKERS_FEED_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return _empty_feed()

    posts: list[SeekerPost] = []
    sources_ok: list[str] = []

    reddit_posts: list[SeekerPost] = []
    try:
        reddit_posts = fetch_reddit_seekers()
        posts.extend(reddit_posts)
        if reddit_posts:
            sources_ok.append("reddit")
    except Exception as exc:
        print(f"seekers reddit failed: {exc}")

    try:
        mp = fetch_marktplaats_seekers()
        posts.extend(mp)
        if mp:
            sources_ok.append("marktplaats")
    except Exception as exc:
        print(f"seekers marktplaats failed: {exc}")

    try:
        fb = load_facebook_seekers_from_cache()
        posts.extend(fb)
        if fb:
            sources_ok.append("facebook")
    except Exception as exc:
        print(f"seekers facebook cache failed: {exc}")

    seen: set[str] = set()
    unique: list[SeekerPost] = []
    for p in posts:
        key = p.url.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    merged = _merge_registry(unique)

    def _sort_key(p: SeekerPost) -> tuple:
        kind_rank = 0 if p.kind == "seeking" else 1 if p.kind == "unknown" else 2
        return (kind_rank, p.posted_at or "")

    merged.sort(key=_sort_key, reverse=True)
    seeking = [p for p in merged if p.kind == "seeking"]
    display = [p for p in merged if p.kind == "seeking"][
        : int(os.getenv("SEEKERS_FEED_MAX", "40"))
    ]
    reddit_merged = [p for p in merged if p.source == "reddit"]
    if reddit_merged and "reddit" not in sources_ok:
        sources_ok.append("reddit")

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources_active": sources_ok,
        "total": len(display),
        "seeking_count": len(seeking),
        "reddit_overview": build_reddit_overview(reddit_merged),
        "posts": [p.to_dict() for p in display],
        "notes": (
            "Automatisch: Reddit + Marktplaats. Facebook alleen lokaal "
            "(python -m src.seekers.facebook_local)."
        ),
    }
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    Path("data/seekers_feed.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    return payload


def _empty_feed() -> dict:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources_active": [],
        "total": 0,
        "seeking_count": 0,
        "posts": [],
        "notes": "",
    }
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
