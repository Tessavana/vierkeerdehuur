import json
from datetime import datetime, timezone
from pathlib import Path


def log_event(event_type: str, payload: dict) -> None:
    path = Path("data/events.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")
