import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    search_urls: list[str]
    max_rent: int
    min_size: int
    poll_interval_seconds: int
    sqlite_path: Path
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str


def load_config() -> AppConfig:
    load_dotenv()
    urls_raw = os.getenv("SEARCH_URLS", "").strip()
    search_urls = [u.strip() for u in urls_raw.split(",") if u.strip()]
    if not search_urls:
        raise ValueError("SEARCH_URLS is required. Add it in .env.")

    return AppConfig(
        search_urls=search_urls,
        max_rent=int(os.getenv("MAX_RENT", "1150")),
        min_size=int(os.getenv("MIN_SIZE", "20")),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
        sqlite_path=Path(os.getenv("SQLITE_PATH", "data/listings.db")),
        telegram_enabled=os.getenv("TELEGRAM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
    )
