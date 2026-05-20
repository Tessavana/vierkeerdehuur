"""Track first-seen for sorting; platform-new flag is set separately."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_REGISTRY_PATH = Path("data/listing_registry.json")


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


def apply_listing_lifecycle(items: list[dict]) -> None:
    """Set first_seen_utc for sorting; prune URLs absent from this run."""
    now = datetime.now(timezone.utc).isoformat()
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
        item["first_seen_utc"] = entry.get("first_seen_utc", now)

    _save(registry)
