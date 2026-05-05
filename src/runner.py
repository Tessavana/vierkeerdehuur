import time

from src.config import AppConfig
from src.events import log_event
from src.filters import is_rental_match, score_rental
from src.notify import notify_console, notify_telegram
from src.providers import ListingProvider
from src.store import ListingStore


def run_once(config: AppConfig, providers: list[ListingProvider], store: ListingStore) -> None:
    for provider in providers:
        try:
            listings = provider.fetch()
        except Exception as exc:
            print(f"provider failed ({provider.__class__.__name__}): {exc}")
            log_event("provider_failed", {"provider": provider.__class__.__name__, "error": str(exc)})
            continue
        for listing in listings:
            if not is_rental_match(listing, config):
                continue
            if not store.is_new_listing(listing):
                continue
            score = score_rental(listing, config)
            store.save_listing(listing)
            notify_console(listing, score)
            try:
                notify_telegram(config, listing, score)
            except Exception as exc:
                print(f"telegram failed: {exc}")
                log_event("telegram_failed", {"error": str(exc), "url": listing.url})


def run_loop(config: AppConfig, providers: list[ListingProvider], store: ListingStore) -> None:
    while True:
        try:
            run_once(config, providers, store)
        except Exception as exc:
            print(f"run failed: {exc}")
        time.sleep(config.poll_interval_seconds)
