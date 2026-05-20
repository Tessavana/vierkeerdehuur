"""Track all discovered listings (in-budget + excluded) for market statistics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_MARKET_PATH = Path("data/market_registry.json")
_AMSTERDAM = ZoneInfo("Europe/Amsterdam")
_STALE_DAYS = 21


def _load() -> dict[str, dict]:
    if not _MARKET_PATH.exists():
        return {}
    try:
        raw = json.loads(_MARKET_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(registry: dict[str, dict]) -> None:
    _MARKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MARKET_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=True), encoding="utf-8")


def _parse_dt(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def record_market_listings(items: list[dict]) -> None:
    """Upsert every listing seen this run (suitable or excluded)."""
    now = datetime.now(timezone.utc).isoformat()
    registry = _load()
    seen_urls: set[str] = set()

    for item in items:
        url = str(item.get("url", "")).strip().lower()
        if not url:
            continue
        seen_urls.add(url)
        entry = registry.get(url) or {}
        if "first_seen_utc" not in entry:
            entry["first_seen_utc"] = now
        entry["last_seen_utc"] = now
        entry["source"] = item.get("source") or item.get("provider_name") or ""
        entry["provider_name"] = item.get("provider_name") or ""
        entry["title"] = item.get("title") or ""
        entry["rent_eur"] = item.get("rent_eur")
        entry["size_m2"] = item.get("size_m2")
        entry["in_budget"] = item.get("in_budget", True)
        entry["exclude_reason"] = item.get("reason") or item.get("exclude_reason")
        registry[url] = entry

    cutoff = datetime.now(timezone.utc) - timedelta(days=_STALE_DAYS)
    for url in list(registry.keys()):
        if url in seen_urls:
            continue
        last = _parse_dt(registry[url].get("last_seen_utc", ""))
        if last and last < cutoff:
            del registry[url]

    _save(registry)


def build_market_stats(
    suitable: list[dict],
    excluded: list[dict],
    max_rent: int,
) -> dict:
    registry = _load()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    all_with_rent: list[dict] = []
    for entry in registry.values():
        rent = entry.get("rent_eur")
        if rent is not None and isinstance(rent, (int, float)):
            all_with_rent.append(entry)

    new_this_week = 0
    for entry in registry.values():
        first = _parse_dt(entry.get("first_seen_utc", ""))
        if first and first >= week_ago:
            new_this_week += 1

    rents_all = [int(e["rent_eur"]) for e in all_with_rent]
    rents_budget = [int(l["rent_eur"]) for l in suitable if l.get("rent_eur") is not None]
    sizes_all = [int(e["size_m2"]) for e in registry.values() if e.get("size_m2") is not None]

    buckets = [
        ("< €800", 0, 800),
        ("€800–999", 800, 1000),
        ("€1000–1149", 1000, max_rent),
        ("€1150–1399", max_rent, 1400),
        ("€1400+", 1400, 100000),
    ]
    distribution = []
    for label, lo, hi in buckets:
        count = sum(1 for r in rents_all if lo <= r < hi)
        distribution.append({"label": label, "count": count})

    by_platform: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for entry in registry.values():
        src = (entry.get("source") or "unknown").lower()
        by_platform[src] = by_platform.get(src, 0) + 1
        if not entry.get("in_budget", True):
            reason = entry.get("exclude_reason") or "other"
            by_reason[reason] = by_reason.get(reason, 0) + 1

    outdoor = sum(1 for l in suitable if l.get("outdoor_space"))
    strijp = sum(
        1
        for l in suitable
        if "strijp" in f"{l.get('title', '')} {l.get('location', '')}".lower()
    )

    eur_per_m2: list[float] = []
    for e in registry.values():
        r, s = e.get("rent_eur"), e.get("size_m2")
        if r and s and s > 0:
            eur_per_m2.append(float(r) / float(s))

    cheapest = min(rents_budget) if rents_budget else None
    priciest_budget = max(rents_budget) if rents_budget else None

    return {
        "total_tracked": len(registry),
        "active_in_budget": len(suitable),
        "active_excluded": len(excluded),
        "new_this_week": new_this_week,
        "new_today": sum(1 for l in suitable if l.get("is_new_today")),
        "avg_rent_all": round(sum(rents_all) / len(rents_all)) if rents_all else None,
        "median_rent_all": _median(rents_all),
        "avg_rent_in_budget": round(sum(rents_budget) / len(rents_budget)) if rents_budget else None,
        "avg_size_m2": round(sum(sizes_all) / len(sizes_all)) if sizes_all else None,
        "avg_eur_per_m2": round(sum(eur_per_m2) / len(eur_per_m2), 2) if eur_per_m2 else None,
        "cheapest_in_budget": cheapest,
        "priciest_in_budget": priciest_budget,
        "pct_above_budget": round(
            100 * sum(1 for e in registry.values() if not e.get("in_budget", True)) / len(registry),
            1,
        )
        if registry
        else 0,
        "outdoor_pct": round(100 * outdoor / len(suitable), 1) if suitable else 0,
        "strijp_in_budget": strijp,
        "price_distribution": distribution,
        "by_platform": dict(sorted(by_platform.items(), key=lambda x: -x[1])),
        "excluded_by_reason": dict(sorted(by_reason.items(), key=lambda x: -x[1])),
    }


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2)
