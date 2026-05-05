import requests

from src.config import AppConfig
from src.events import log_event
from src.models import Listing


def notify_console(listing: Listing, score: int) -> None:
    print("\n[NEW MATCH]")
    print(f"Source: {listing.source}")
    print(f"Title: {listing.title}")
    print(f"Location: {listing.location}")
    print(f"Rent: {listing.rent_eur if listing.rent_eur is not None else 'unknown'}")
    print(f"Size: {listing.size_m2 if listing.size_m2 is not None else 'unknown'}")
    if listing.available_from:
        print(f"Available from: {listing.available_from}")
    print(f"Outdoor: {'yes' if listing.outdoor_space else 'unknown/no'}")
    print(f"Score: {score}")
    print(f"Link: {listing.url}")
    log_event(
        "console_notification",
        {"source": listing.source, "url": listing.url, "score": score, "title": listing.title},
    )


def notify_telegram(config: AppConfig, listing: Listing, score: int) -> None:
    if not config.telegram_enabled:
        return
    if not config.telegram_bot_token or not config.telegram_chat_id:
        print("telegram skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return
    text = _build_telegram_message(listing, score)
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload = {"chat_id": config.telegram_chat_id, "text": text, "disable_web_page_preview": True}
    response = requests.post(url, data=payload, timeout=20)
    response.raise_for_status()
    log_event(
        "telegram_notification_sent",
        {"source": listing.source, "url": listing.url, "score": score, "chat_id": config.telegram_chat_id},
    )


def _build_telegram_message(listing: Listing, score: int) -> str:
    rent = listing.rent_eur if listing.rent_eur is not None else "unknown"
    size = listing.size_m2 if listing.size_m2 is not None else "unknown"
    outdoor = "yes" if listing.outdoor_space else "unknown/no"
    return (
        "[NEW MATCH]\n"
        f"Source: {listing.source}\n"
        f"Title: {listing.title}\n"
        f"Location: {listing.location}\n"
        f"Rent: {rent}\n"
        f"Size: {size}\n"
        f"Outdoor: {outdoor}\n"
        f"Available: {listing.available_from or 'unknown'}\n"
        f"Score: {score}\n"
        f"Link: {listing.url}"
    )
