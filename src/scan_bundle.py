"""Persist last suitable listings per provider for incremental scan rotations."""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.scan_schedule import bundle_enabled

BUNDLE_PATH = Path("data/scan_bundle.json")


def load_scan_bundle() -> dict[str, list[dict]]:
    if not bundle_enabled():
        return {}
    if not BUNDLE_PATH.exists():
        return {}
    try:
        data = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        raw = data.get("listings_by_provider")
        if isinstance(raw, dict):
            return {str(k): v for k, v in raw.items() if isinstance(v, list)}
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_scan_bundle(bundle: dict[str, list[dict]]) -> None:
    if not bundle_enabled():
        return
    BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "listings_by_provider": bundle,
    }
    BUNDLE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
