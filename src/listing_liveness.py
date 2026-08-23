"""Verify listing URLs still point to live rental pages (parallel + cached)."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

_COMMON_DEAD = (
    "niet meer beschikbaar",
    "niet langer beschikbaar",
    "deze advertentie is verwijderd",
    "advertentie niet gevonden",
    "woning is verhuurd",
    "is verhuurd",
    "reeds verhuurd",
    "aanmelding gesloten",
    "inschrijving gesloten",
    "geen woning gevonden",
    "pagina niet gevonden",
    "404 not found",
    "page not found",
    "niet beschikbaar",
    "verhuurd",
    "archief",
)

_SOURCE_DEAD: dict[str, tuple[str, ...]] = {
    "rentfinder": (
        "property not found",
        "niet gevonden",
        "is verhuurd",
        "niet meer beschikbaar",
    ),
    "vbt": (
        "niet beschikbaar",
        "verhuurd",
        "deze woning is niet meer beschikbaar",
        "woning is verhuurd",
    ),
    "huurwoningen": _COMMON_DEAD,
    "pararius": (
        "niet meer beschikbaar",
        "deze woning is verhuurd",
        "advertentie is offline",
    ),
}

_HEADERS = {"User-Agent": "vierkeerdehuur/1.0 (listing liveness check)"}
_CACHE_PATH = Path(os.getenv("LIVENESS_CACHE_PATH", "data/liveness_cache.json"))


def _dead_markers(source: str) -> tuple[str, ...]:
    key = (source or "").lower()
    extra = _SOURCE_DEAD.get(key, ())
    return _COMMON_DEAD + extra


def _liveness_enabled(enabled: bool | None) -> bool:
    if enabled is not None:
        return enabled
    return os.getenv("LISTING_LIVENESS_CHECK", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _ttl_alive() -> float:
    return float(os.getenv("LISTING_LIVENESS_TTL_ALIVE", str(4 * 3600)))


def _ttl_dead() -> float:
    return float(os.getenv("LISTING_LIVENESS_TTL_DEAD", "3600"))


def _max_workers() -> int:
    return max(1, int(os.getenv("LISTING_LIVENESS_WORKERS", "12")))


def _load_cache() -> dict[str, dict[str, Any]]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict[str, dict[str, Any]]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _cache_fresh(entry: dict[str, Any] | None) -> bool:
    if not entry or "ts" not in entry:
        return False
    age = time.time() - float(entry["ts"])
    if entry.get("alive"):
        return age < _ttl_alive()
    return age < _ttl_dead()


def _body_indicates_dead(text: str, source: str) -> bool:
    text = text[:120_000].lower()
    markers = _dead_markers(source)
    hits = sum(1 for m in markers if m in text)
    if "niet meer beschikbaar" in text or "advertentie is verwijderd" in text:
        return True
    if hits >= 2 and any(m in text for m in ("verhuurd", "niet beschikbaar", "archief")):
        return True
    if source == "rentfinder" and "property not found" in text:
        return True
    return False


def url_looks_alive(url: str, source: str = "", timeout: float = 10.0) -> bool:
    """Return False when URL is clearly dead (404, gone, verhuurd markers)."""
    if not url or not url.startswith("http"):
        return False
    try:
        resp = requests.head(
            url,
            headers=_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code in {404, 410, 451}:
            return False
        if resp.status_code in {405, 501} or resp.status_code >= 500:
            resp = requests.get(
                url,
                headers=_HEADERS,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
        elif resp.status_code >= 400:
            return False
        else:
            # HEAD ok — still need body for "verhuurd" markers on some sites.
            resp = requests.get(
                url,
                headers=_HEADERS,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
    except requests.RequestException:
        return False

    if resp.status_code in {404, 410, 451}:
        return False
    if resp.status_code >= 500:
        return True

    chunks: list[bytes] = []
    size = 0
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size >= 120_000:
            break
    try:
        resp.close()
    except Exception:
        pass
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return not _body_indicates_dead(text, source)


def _check_one(url: str, source: str, cache: dict[str, dict[str, Any]]) -> tuple[str, bool, bool]:
    """Returns (url, alive, from_cache)."""
    entry = cache.get(url)
    if _cache_fresh(entry):
        return url, bool(entry.get("alive")), True
    alive = url_looks_alive(url, source)
    cache[url] = {"alive": alive, "ts": time.time(), "source": source}
    return url, alive, False


def filter_alive_listings(
    items: list[dict[str, Any]], *, enabled: bool | None = None, force_refresh: bool = False
) -> tuple[list[dict], int]:
    """Drop listings whose URL fails liveness check. Returns (alive, removed_count)."""
    if not _liveness_enabled(enabled) or not items:
        return items, 0

    cache = _load_cache()
    if force_refresh:
        for item in items:
            url = (item.get("url") or "").strip()
            if url:
                cache.pop(url, None)

    to_check: list[tuple[str, str, dict[str, Any]]] = []
    skipped_alive: list[dict] = []
    for item in items:
        url = (item.get("url") or "").strip()
        source = item.get("source") or ""
        if not url:
            continue
        entry = cache.get(url)
        if _cache_fresh(entry) and entry.get("alive"):
            skipped_alive.append(item)
        else:
            to_check.append((url, source, item))

    removed = 0
    alive: list[dict] = list(skipped_alive)
    if not to_check:
        _save_cache(cache)
        return alive, removed

    workers = min(_max_workers(), len(to_check))
    results: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_check_one, url, source, cache): (url, item)
            for url, source, item in to_check
        }
        for fut in as_completed(futures):
            url, item = futures[fut]
            try:
                _, is_alive, _ = fut.result()
                results[url] = is_alive
            except Exception:
                results[url] = True

    for url, source, item in to_check:
        if results.get(url, True):
            alive.append(item)
        else:
            removed += 1
            print(f"liveness: dropped dead URL ({source}): {url[:80]}")

    _save_cache(cache)
    return alive, removed
