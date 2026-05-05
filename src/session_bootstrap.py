import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def bootstrap_session(url: str, out_path: str, wait_seconds: int) -> None:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="nl-NL")
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"Opened {url}")
        print("Complete any human checks/login in the browser window.")
        print(f"Waiting {wait_seconds} seconds before saving session state...")
        page.wait_for_timeout(wait_seconds * 1000)
        context.storage_state(path=str(target))
        print(f"Saved storage state to: {target}")
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Playwright authenticated session state.")
    parser.add_argument("--url", default="https://www.pararius.com/apartments/eindhoven")
    parser.add_argument("--out", default="data/playwright_state.json")
    parser.add_argument("--wait-seconds", type=int, default=90)
    args = parser.parse_args()
    bootstrap_session(args.url, args.out, args.wait_seconds)


if __name__ == "__main__":
    main()
