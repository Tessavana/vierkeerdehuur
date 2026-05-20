import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

_DEFAULT_URLS = (
    "https://www.funda.nl/zoeken/huur?selected_area=%5B%22eindhoven%22%5D",
    "https://www.pararius.com/apartments/eindhoven",
)


def bootstrap_session(urls: list[str], out_path: str, wait_seconds: int) -> None:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="nl-NL")
        page = context.new_page()
        for url in urls:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            print(f"Opened {url}")
            for sel in (
                "button#onetrust-accept-btn-handler",
                "button:has-text('Accepteren')",
                "button:has-text('Alles accepteren')",
            ):
                try:
                    if page.locator(sel).count():
                        page.locator(sel).first.click(timeout=4000)
                        break
                except Exception:
                    pass
            print("Complete any human checks in the browser window, then wait…")
        print(f"Waiting {wait_seconds} seconds before saving session state…")
        page.wait_for_timeout(wait_seconds * 1000)
        context.storage_state(path=str(target))
        print(f"Saved storage state to: {target}")
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap Playwright session (Funda + Pararius anti-bot cookies)."
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Page to open (repeat for multiple). Default: Funda + Pararius Eindhoven huur.",
    )
    parser.add_argument("--out", default="data/playwright_state.json")
    parser.add_argument("--wait-seconds", type=int, default=120)
    args = parser.parse_args()
    urls = args.urls if args.urls else list(_DEFAULT_URLS)
    bootstrap_session(urls, args.out, args.wait_seconds)


if __name__ == "__main__":
    main()
