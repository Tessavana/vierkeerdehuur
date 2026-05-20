"""Track first-seen dates and drop listings no longer returned by scrapers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_REGISTRY_PATH = Path("data/listing_registry.json")
_AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def _load() -> dict[str, dict[str, str]]:
    if not _REGISTRY_PATH.exists():
        return {}
    try:
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(registry: dict[str, dict[str, str]]) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=True), encoding="utf-8")


def _today_amsterdam() -> str:
    return datetime.now(_AMSTERDAM).date().isoformat()


def apply_listing_lifecycle(items: list[dict]) -> None:
    """Set first_seen_utc / is_new_today; prune URLs absent from this run."""
    now = datetime.now(timezone.utc).isoformat()
    today = _today_amsterdam()
    active_urls = {str(i.get("url", "")).strip().lower() for i in items if i.get("url")}
    registry = _load()

    for url in list(registry.keys()):
        if url not in active_urls:
            del registry[url]

    for item in items:
        url = str(item.get("url", "")).strip().lower()
        if not url:
            continue
        entry = registry.get(url)
        if not entry:
            entry = {"first_seen_utc": now, "last_seen_utc": now}
            registry[url] = entry
        else:
            entry["last_seen_utc"] = now
        first = entry.get("first_seen_utc", now)
        item["first_seen_utc"] = first
        try:
            first_day = datetime.fromisoformat(first.replace("Z", "+00:00")).astimezone(_AMSTERDAM).date().isoformat()
        except ValueError:
            first_day = today
        item["is_new_today"] = first_day == today

    _save(registry)
