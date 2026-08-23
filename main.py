import argparse

from src.config import load_config
from src.provider_registry import build_providers
from src.runner import run_loop, run_once
from src.scan_schedule import filter_providers_for_incremental
from src.status_app import run_status_server
from src.store import ListingStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="4xIncomeNoKeys housing scraper")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--status-server", action="store_true", help="Run localhost status dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Status dashboard port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.status_server:
        run_status_server(port=args.port)
        return
    config = load_config()
    providers = filter_providers_for_incremental(build_providers(config.search_urls))
    store = ListingStore(config.sqlite_path)
    if args.once:
        run_once(config, providers, store)
        return
    run_loop(config, providers, store)


if __name__ == "__main__":
    main()
