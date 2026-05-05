import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.filters import evaluate_rental, score_rental
from src.providers import (
    FundaProvider,
    HuislijnProvider,
    HuurwoningenProvider,
    JsonFileProvider,
    KamernetProvider,
    ListingProvider,
    ParariusProvider,
    RentfinderProvider,
    VbtProvider,
    VestedaProvider,
)


def run_workrun() -> dict:
    config = load_config()
    providers = _build_providers(config.search_urls)
    provider_results: list[dict] = []
    all_matches: list[dict] = []
    excluded_items: list[dict] = []

    for provider in providers:
        provider_name = provider.__class__.__name__
        try:
            listings = provider.fetch()
            suitable: list = []
            excluded_count = 0
            for listing in listings:
                ok, reason = evaluate_rental(listing, config)
                if ok:
                    suitable.append(listing)
                else:
                    excluded_count += 1
                    excluded_items.append(
                        {
                            "provider": provider_name,
                            "provider_name": _clean_provider_name(provider_name),
                            "source": listing.source,
                            "title": listing.title,
                            "location": listing.location,
                            "rent_eur": listing.rent_eur,
                            "size_m2": listing.size_m2,
                            "url": listing.url,
                            "reason": reason,
                            "neighborhood": _extract_neighborhood(listing.title, listing.location),
                            "available_from": listing.available_from,
                        }
                    )
            normalized = [
                {
                    "provider": provider_name,
                    "provider_name": _clean_provider_name(provider_name),
                    "source": l.source,
                    "title": l.title,
                    "location": l.location,
                    "rent_eur": l.rent_eur,
                    "size_m2": l.size_m2,
                    "outdoor_space": l.outdoor_space,
                    "url": l.url,
                    "match_tag": _match_tag(score_rental(l, config)),
                    "neighborhood": _extract_neighborhood(l.title, l.location),
                    "available_from": l.available_from,
                }
                for l in suitable
            ]
            all_matches.extend(normalized)
            provider_results.append(
                {
                    "provider": provider_name,
                    "provider_name": _clean_provider_name(provider_name),
                    "status": "ok",
                    "parsed": len(listings),
                    "suitable": len(suitable),
                    "excluded": excluded_count,
                    "error": None,
                }
            )
        except Exception as exc:
            provider_results.append(
                {
                    "provider": provider_name,
                    "provider_name": _clean_provider_name(provider_name),
                    "status": "error",
                    "parsed": 0,
                    "suitable": 0,
                    "excluded": 0,
                    "error": str(exc),
                }
            )

    deduped = _dedupe_by_url(all_matches)
    deduped.sort(key=lambda x: (x["rent_eur"] is None, -(x["rent_eur"] or 10**9)), reverse=False)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "city": "Eindhoven",
        "max_rent": config.max_rent,
        "provider_results": provider_results,
        "listings": deduped,
        "excluded_listings": excluded_items,
        "application_status": _load_application_status(),
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
        elif "huislijn.nl" in lower:
            providers.append(HuislijnProvider(url))
        elif "huurwoningen.nl" in lower:
            providers.append(HuurwoningenProvider(url))
        elif "rentfinder" in lower:
            providers.append(RentfinderProvider(url))
        else:
            providers.append(ParariusProvider(url))
    return providers


def _load_application_status() -> dict:
    path = Path("data/application_status.json")
    if not path.exists():
        return {
            "applications_sent": 5,
            "viewings": 0,
            "rejections": 3,
            "no_response": 4,
            "rejected_addresses": ["PSV-laan 233", "Schootsestraat 94 A"],
            "sociale_huur": {
                "platform": "Wooniezie",
                "inschrijfduur": "4 jaar en 3 maanden",
                "reacties_verstuurd": "230+",
                "actief_gezocht": "2 jaar",
                "bezichtigingen": 0,
            },
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_provider_name(name: str) -> str:
    return name.replace("Provider", "")


def _match_tag(score: int) -> str:
    if score >= 45:
        return "Instant reageren"
    if score >= 20:
        return "Kansrijk"
    return "Twijfelgeval"


def _extract_neighborhood(title: str, location: str) -> str:
    searchable = f"{title} {location}".lower()
    # Longer phrases first so "strijp-s" wins over "strijp".
    hits = [
        ("strijp-s", "Strijp"),
        ("strijp", "Strijp"),
        ("meerrijk", "Meerrijk"),
        ("blixembosch", "Blixembosch"),
        ("centrum", "Centrum"),
        ("stratum", "Stratum"),
        ("woensel", "Woensel"),
        ("tongelre", "Tongelre"),
        ("gestel", "Gestel"),
        ("bergen", "Bergen"),
        ("vonderkwartier", "Vonderkwartier"),
        ("engelsbergen", "Engelsbergen"),
        ("schrijversbuurt", "Schrijversbuurt"),
        ("genneper", "Genneper"),
        ("vaartbroek", "Vaartbroek"),
        ("het regentekwartier", "Centrum"),
        ("regentekwartier", "Centrum"),
    ]
    for needle, label in hits:
        if needle in searchable:
            return label
    return ""


if __name__ == "__main__":
    result = run_workrun()
    print(f"Generated {len(result['listings'])} listing(s) from {len(result['provider_results'])} provider(s).")
