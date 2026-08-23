import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.filters import evaluate_rental, score_rental
from src.listing_detail import enrich_listing, is_new_on_platform_today, normalize_available_from
from src.listing_registry import apply_listing_lifecycle
from src.market_registry import build_market_stats, record_market_listings
from src.eindhoven_geo import attach_map_coordinates
from src.scan_bundle import load_scan_bundle, save_scan_bundle
from src.scan_schedule import provider_should_fetch_live
from src.seekers.build_feed import build_seekers_feed
from src.providers import (
    FundaProvider,
    HuislijnProvider,
    HuurwoningenProvider,
    JsonFileProvider,
    KamernetProvider,
    ListingProvider,
    NmgProvider,
    ParariusProvider,
    RentfinderProvider,
    RotsvastProvider,
    VbtProvider,
    VestedaProvider,
)


def run_workrun() -> dict:
    config = load_config()
    providers = _build_providers(config.search_urls)
    bundle = load_scan_bundle()
    provider_results: list[dict] = []
    all_matches: list[dict] = []
    excluded_items: list[dict] = []

    for provider in providers:
        provider_name = provider.__class__.__name__
        live = provider_should_fetch_live(provider_name)
        cached = bundle.get(provider_name) if not live else None
        if not live and cached:
            all_matches.extend(cached)
            provider_results.append(
                {
                    "provider": provider_name,
                    "provider_name": _clean_provider_name(provider_name),
                    "status": "cached",
                    "parsed": len(cached),
                    "suitable": len(cached),
                    "excluded": 0,
                    "error": None,
                }
            )
            continue

        if not live and not cached:
            live = True

        try:
            listings = provider.fetch()
            suitable: list = []
            excluded_count = 0
            for listing in listings:
                listing = _maybe_enrich(listing)
                ok, reason = evaluate_rental(listing, config)
                if ok:
                    suitable.append(listing)
                else:
                    excluded_count += 1
                    excluded_items.append(
                        {
                            "provider": provider_name,
                            "platform": _platform_label(
                                listing.source, _clean_provider_name(provider_name)
                            ),
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
                            "notes": listing.notes,
                        }
                    )
            normalized = [
                {
                    "provider": provider_name,
                    "platform": _platform_label(l.source, _clean_provider_name(provider_name)),
                    "provider_name": _clean_provider_name(provider_name),
                    "source": l.source,
                    "title": l.title,
                    "location": l.location,
                    "rent_eur": l.rent_eur,
                    "size_m2": l.size_m2,
                    "outdoor_space": l.outdoor_space,
                    "outdoor_known": l.outdoor_known,
                    "url": l.url,
                    "match_tag": _match_tag(score_rental(l, config)),
                    "neighborhood": _extract_neighborhood(l.title, l.location),
                    "available_from": normalize_available_from(l.available_from),
                    "platform_listed_date": l.platform_listed_date,
                    "is_new_today": is_new_on_platform_today(l),
                    "notes": l.notes,
                    "map_lat": l.map_lat,
                    "map_lon": l.map_lon,
                }
                for l in suitable
            ]
            all_matches.extend(normalized)
            bundle[provider_name] = normalized
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
            fallback = bundle.get(provider_name)
            if fallback:
                all_matches.extend(fallback)
                provider_results.append(
                    {
                        "provider": provider_name,
                        "provider_name": _clean_provider_name(provider_name),
                        "status": "error_fallback_cache",
                        "parsed": len(fallback),
                        "suitable": len(fallback),
                        "excluded": 0,
                        "error": str(exc),
                    }
                )
            else:
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

    save_scan_bundle(bundle)

    deduped = _dedupe_by_url(all_matches)
    apply_listing_lifecycle(deduped)
    deduped.sort(key=_sort_newest_first)

    market_rows = [
        {**item, "in_budget": True}
        for item in deduped
    ] + [
        {**item, "in_budget": False}
        for item in excluded_items
    ]
    record_market_listings(market_rows)
    market_stats = build_market_stats(deduped, excluded_items, config.max_rent)

    attach_map_coordinates(deduped)
    seekers_feed = build_seekers_feed()
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "city": "Eindhoven",
        "max_rent": config.max_rent,
        "scan_profile": os.getenv("SCAN_PROFILE", "full"),
        "provider_results": provider_results,
        "listings": deduped,
        "excluded_listings": excluded_items,
        "market_stats": market_stats,
        "application_status": _load_application_status(),
        "seekers_feed": seekers_feed,
    }
    _write_outputs(payload)
    return payload


def _write_outputs(payload: dict) -> None:
    docs_data = Path("docs/data")
    docs_data.mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    (docs_data / "latest_listings.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    (Path("data") / "latest_listings.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _maybe_enrich(listing):
    if listing.notes and len(listing.notes) > 250 and listing.platform_listed_date:
        return listing
    if listing.notes and len(listing.notes) > 800:
        return listing
    return enrich_listing(listing)


def _sort_newest_first(item: dict) -> tuple:
    raw = item.get("first_seen_utc") or ""
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        ts = 0.0
    listed = item.get("platform_listed_date") or ""
    return (-ts, listed, not item.get("is_new_today", False))


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
        elif "rotsvast.nl" in lower:
            providers.append(RotsvastProvider(url))
        elif "nmgwonen.nl" in lower or "nmg.nl" in lower:
            providers.append(NmgProvider(url))
        elif "huislijn.nl" in lower:
            providers.append(HuislijnProvider(url))
        elif "huurwoningen.nl" in lower or "huurwoningen.com" in lower:
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
            "reacties_verstuurd": 46,
            "bezichtigingen": 0,
            "kijkavonden": 2,
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


def _platform_label(source: str, provider_name: str) -> str:
    labels = {
        "funda": "Funda",
        "vbt": "VB&T",
        "vesteda": "Vesteda",
        "rotsvast": "Rotsvast",
        "nmg": "NMG",
        "pararius": "Pararius",
        "kamernet": "Kamernet",
        "huurwoningen": "Huurwoningen",
        "huislijn": "Huislijn",
        "rentfinder": "Rentfinder",
    }
    return labels.get((source or "").lower(), provider_name or source or "?")


def _match_tag(score: int) -> str:
    if score >= 50:
        return "super nice"
    if score >= 30:
        return "nice"
    if score >= 12:
        return "okay"
    return "meh"


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
