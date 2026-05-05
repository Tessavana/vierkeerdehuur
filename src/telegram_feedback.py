import argparse
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

STATUS_FILE = Path("data/application_status.json")
OFFSET_FILE = Path("data/telegram_offset.txt")


def sync_feedback() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("telegram feedback sync skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return

    offset = _read_offset()
    updates_url = f"https://api.telegram.org/bot{token}/getUpdates"
    response = requests.get(updates_url, params={"offset": offset, "timeout": 2}, timeout=20)
    response.raise_for_status()
    updates = response.json().get("result", [])
    state = _load_state()

    for update in updates:
        update_id = int(update.get("update_id", 0))
        msg = update.get("message", {})
        if str(msg.get("chat", {}).get("id", "")) != chat_id:
            _write_offset(update_id + 1)
            continue
        text = str(msg.get("text", "")).strip()
        _apply_command(state, text)
        _write_offset(update_id + 1)

    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"synced {len(updates)} telegram update(s)")


def _apply_command(state: dict, text: str) -> None:
    normalized = " ".join(text.strip().split())
    lowered = normalized.lower()

    if lowered.startswith("/applied "):
        state["applications_sent"] = int(state.get("applications_sent", 0)) + 1
    elif lowered.startswith("/viewing "):
        state["viewings"] = int(state.get("viewings", 0)) + 1
    elif lowered.startswith("/rejected "):
        state["rejections"] = int(state.get("rejections", 0)) + 1
        address = normalized[10:].strip().strip("<>").strip()
        if address:
            state.setdefault("rejected_addresses", []).append(address)
    elif lowered.startswith("/noresponse "):
        state["no_response"] = int(state.get("no_response", 0)) + 1


def _load_state() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    return {
        "applications_sent": 5,
        "viewings": 0,
        "rejections": 3,
        "no_response": 2,
        "rejected_addresses": ["PSV-laan 233", "Schootsestraat 94 A"],
        "sociale_huur": {
            "platform": "Wooniezie",
            "inschrijfduur": "4 jaar en 3 maanden",
            "reacties_verstuurd": "230+",
            "actief_gezocht": "2 jaar",
            "bezichtigingen": 0,
        },
    }


def _read_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            return 0
    return 0


def _write_offset(value: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(value), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Telegram status commands into application status data.")
    parser.parse_args()
    sync_feedback()
