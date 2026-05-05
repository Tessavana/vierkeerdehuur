import json
import os
import sqlite3
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="4xIncomeNoKeys Status")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/api/status")
def api_status() -> JSONResponse:
    db_path = os.getenv("SQLITE_PATH", "data/listings.db")
    listings_count = _count_listings(db_path)
    events = _read_events(limit=40)
    return JSONResponse(
        {
            "database": {"path": db_path, "listings_count": listings_count},
            "telegram": {
                "enabled": os.getenv("TELEGRAM_ENABLED", "false"),
                "chat_id_set": bool(os.getenv("TELEGRAM_CHAT_ID", "").strip()),
                "token_set": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
            },
            "github_actions": {"workflow_exists": Path(".github/workflows/housing-scan.yml").exists()},
            "recent_events": events,
        }
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    status = api_status().body.decode("utf-8")
    payload = json.loads(status)
    rows = []
    for ev in payload["recent_events"][-20:][::-1]:
        rows.append(
            f"<tr><td>{ev.get('ts','')}</td><td>{ev.get('type','')}</td>"
            f"<td><pre>{json.dumps(ev.get('payload', {}), ensure_ascii=True)}</pre></td></tr>"
        )
    events_html = "".join(rows) or "<tr><td colspan='3'>No events yet</td></tr>"
    return f"""
    <html>
      <head>
        <title>4xIncomeNoKeys Status</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 20px; }}
          .ok {{ color: #0a7d15; }}
          table {{ border-collapse: collapse; width: 100%; }}
          td, th {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
          pre {{ margin: 0; white-space: pre-wrap; }}
        </style>
      </head>
      <body>
        <h1>4xIncomeNoKeys Local Status</h1>
        <p><b>Database listings:</b> {payload["database"]["listings_count"]}</p>
        <p><b>Telegram enabled:</b> {payload["telegram"]["enabled"]} |
           <b>Token set:</b> {payload["telegram"]["token_set"]} |
           <b>Chat ID set:</b> {payload["telegram"]["chat_id_set"]}</p>
        <p><b>GitHub Actions workflow file:</b> {payload["github_actions"]["workflow_exists"]}</p>
        <p class="ok">API: <a href="/api/status">/api/status</a> | Health: <a href="/health">/health</a></p>
        <h2>Recent Events</h2>
        <table>
          <tr><th>Timestamp</th><th>Type</th><th>Payload</th></tr>
          {events_html}
        </table>
      </body>
    </html>
    """


def run_status_server(port: int = 8080) -> None:
    uvicorn.run("src.status_app:app", host="127.0.0.1", port=port, reload=False)


def _count_listings(db_path: str) -> int:
    if not Path(db_path).exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM listings").fetchone()
    return int(row[0]) if row else 0


def _read_events(limit: int = 50) -> list[dict]:
    path = Path("data/events.log")
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict] = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
