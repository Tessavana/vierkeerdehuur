import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.filters import is_rental_match, score_rental
from src.providers import (
    FundaProvider,
    JsonFileProvider,
    KamernetProvider,
    ListingProvider,
    ParariusProvider,
    VbtProvider,
    VestedaProvider,
)


def run_workrun() -> dict:
    config = load_config()
    providers = _build_providers(config.search_urls)
    provider_results: list[dict] = []
    all_matches: list[dict] = []

    for provider in providers:
        provider_name = provider.__class__.__name__
        try:
            listings = provider.fetch()
            suitable = [l for l in listings if is_rental_match(l, config)]
            normalized = [
                {
                    "source": l.source,
                    "title": l.title,
                    "location": l.location,
                    "rent_eur": l.rent_eur,
                    "size_m2": l.size_m2,
                    "outdoor_space": l.outdoor_space,
                    "url": l.url,
                    "score": score_rental(l, config),
                }
                for l in suitable
            ]
            all_matches.extend(normalized)
            provider_results.append(
                {
                    "provider": provider_name,
                    "status": "ok",
                    "parsed": len(listings),
                    "suitable": len(suitable),
                    "error": None,
                }
            )
        except Exception as exc:
            provider_results.append(
                {
                    "provider": provider_name,
                    "status": "error",
                    "parsed": 0,
                    "suitable": 0,
                    "error": str(exc),
                }
            )

    deduped = _dedupe_by_url(all_matches)
    deduped.sort(key=lambda x: (x["score"], x["rent_eur"] is None, x["rent_eur"] or 10**9), reverse=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "city": "Eindhoven",
        "max_rent": config.max_rent,
        "provider_results": provider_results,
        "listings": deduped,
    }
    _write_outputs(payload)
    return payload


def _write_outputs(payload: dict) -> None:
    docs_data = Path("docs/data")
    docs_data.mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    (docs_data / "latest_listings.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    (Path("data") / "latest_listings.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _dedupe_by_url(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = item["url"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _build_providers(urls: list[str]) -> list[ListingProvider]:
    providers: list[ListingProvider] = []
    for url in urls:
        lower = url.lower()
        if url.startswith("file://"):
            providers.append(JsonFileProvider(Path(url.replace("file://", "", 1))))
        elif "kamernet.nl" in lower:
            providers.append(KamernetProvider(url))
        elif "funda.nl" in lower:
            providers.append(FundaProvider(url))
        elif "vbt" in lower:
            providers.append(VbtProvider(url))
        elif "vesteda.com" in lower:
            providers.append(VestedaProvider(url))
        else:
            providers.append(ParariusProvider(url))
    return providers


if __name__ == "__main__":
    result = run_workrun()
    print(f"Generated {len(result['listings'])} listing(s) from {len(result['provider_results'])} provider(s).")
