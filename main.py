import argparse
from pathlib import Path

from src.config import load_config
from src.providers import (
    FundaProvider,
    JsonFileProvider,
    KamernetProvider,
    ListingProvider,
    ParariusProvider,
    VbtProvider,
    VestedaProvider,
)
from src.runner import run_loop, run_once
from src.status_app import run_status_server
from src.store import ListingStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="4xIncomeNoKeys housing scraper")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--status-server", action="store_true", help="Run localhost status dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Status dashboard port")
    return parser.parse_args()


def build_providers(urls: list[str]) -> list[ListingProvider]:
    providers: list[ListingProvider] = []
    for url in urls:
        url_lower = url.lower()
        if url.startswith("file://"):
            providers.append(JsonFileProvider(Path(url.replace("file://", "", 1))))
        elif "kamernet.nl" in url_lower:
            providers.append(KamernetProvider(url))
        elif "funda.nl" in url_lower:
            providers.append(FundaProvider(url))
        elif "vbt" in url_lower:
            providers.append(VbtProvider(url))
        elif "vesteda.com" in url_lower:
            providers.append(VestedaProvider(url))
        else:
            providers.append(ParariusProvider(url))
    return providers


def main() -> None:
    args = parse_args()
    if args.status_server:
        run_status_server(port=args.port)
        return
    config = load_config()
    providers = build_providers(config.search_urls)
    store = ListingStore(config.sqlite_path)
    if args.once:
        run_once(config, providers, store)
        return
    run_loop(config, providers, store)


if __name__ == "__main__":
    main()
