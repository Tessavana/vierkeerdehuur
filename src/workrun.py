import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.filters import evaluate_rental, score_rental
from src.listing_detail import enrich_listing, is_new_on_platform_today, normalize_available_from
from src.application_count import attach_application_count
from src.income_requirement import attach_income_requirement, extract_income_requirement, apply_platform_income_defaults
from src.listing_dedupe import dedupe_listings
from src.listing_llm_extract import maybe_llm_fill_listing
from src.listing_liveness import filter_alive_listings
from src.market_registry import build_market_stats, record_market_listings
from src.eindhoven_geo import attach_map_coordinates
from src.neighborhood import resolve_neighborhood
from src.scan_bundle import load_scan_bundle, save_scan_bundle
from src.listing_registry import apply_listing_lifecycle
from src.scan_schedule import scan_profile, provider_should_fetch_live, _HEAVY_PROVIDERS
from src.seekers.build_feed import build_seekers_feed
from src.provider_registry import build_providers


def run_workrun() -> dict:
    config = load_config()
    providers = build_providers(config.search_urls)
    bundle = load_scan_bundle()
    provider_results: list[dict] = []
    all_matches: list[dict] = []
    excluded_items: list[dict] = []

    for provider in providers:
        provider_name = provider.__class__.__name__
        live = provider_should_fetch_live(provider_name)
        cached = bundle.get(provider_name) if not live else None
        if not live and cached:
            validated, dropped = filter_alive_listings(cached)
            if not validated:
                live = True
            else:
                all_matches.extend(validated)
                provider_results.append(
                    {
                        "provider": provider_name,
                        "provider_name": _clean_provider_name(provider_name),
                        "status": "cached",
                        "parsed": len(cached),
                        "suitable": len(validated),
                        "excluded": dropped,
                        "error": None if not dropped else f"{dropped} dead URL(s) removed from cache",
                    }
                )
                continue

        if not live and not cached:
            if scan_profile() == "fast" and provider_name in _HEAVY_PROVIDERS:
                provider_results.append(
                    {
                        "provider": provider_name,
                        "provider_name": _clean_provider_name(provider_name),
                        "status": "skipped",
                        "parsed": 0,
                        "suitable": 0,
                        "excluded": 0,
                        "error": None,
                    }
                )
                continue
            live = True

        try:
            listings = provider.fetch()
            suitable: list = []
            excluded_count = 0
            for listing in listings:
                listing = _maybe_enrich(listing)
                ok, reason = evaluate_rental(listing, config)
                if ok:
                    refresh_apps = scan_profile() != "fast"
                    listing = attach_application_count(listing, force_refresh=refresh_apps)
                    listing = attach_income_requirement(listing)
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
                            "neighborhood": resolve_neighborhood(listing.title, listing.location, listing.notes or ""),
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
                    "neighborhood": resolve_neighborhood(l.title, l.location, l.notes or ""),
                    "available_from": normalize_available_from(l.available_from),
                    "platform_listed_date": l.platform_listed_date,
                    "application_count": l.application_count,
                    "application_count_label": l.application_count_label,
                    "income_multiplier": l.income_multiplier,
                    "income_required_eur": l.income_required_eur,
                    "income_requirement_label": l.income_requirement_label,
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

    deduped, dupe_count = dedupe_listings(all_matches)
    if dupe_count:
        print(f"deduped {dupe_count} duplicate listing(s)")
    deduped, dead_count = filter_alive_listings(deduped)
    if dead_count:
        print(f"liveness: removed {dead_count} dead listing(s) after dedupe")
    deduped = [_ensure_income_fields(item) for item in deduped]
    apply_listing_lifecycle(deduped)
    deduped.sort(key=_sort_newest_first)

    attach_map_coordinates(deduped)
    deduped = [_ensure_neighborhood(item) for item in deduped]

    market_rows = [
        {**item, "in_budget": True}
        for item in deduped
    ] + [
        {**item, "in_budget": False}
        for item in excluded_items
    ]
    record_market_listings(market_rows)
    market_stats = build_market_stats(deduped, excluded_items, config.max_rent)

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
        "duplicate_listings_removed": dupe_count,
        "dead_listings_removed": dead_count,
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
    cache_path = Path(os.getenv("GEOCODE_CACHE_PATH", "data/geocode_cache.json"))
    if cache_path.exists():
        try:
            shutil.copy(cache_path, docs_data / "geocode_cache.json")
        except OSError:
            pass


def _ensure_income_fields(item: dict) -> dict:
    platform_defaults = apply_platform_income_defaults(
        source=item.get("source") or "",
        platform=item.get("platform") or "",
        rent_eur=item.get("rent_eur"),
    )
    if platform_defaults:
        return {**item, **platform_defaults}
    if item.get("income_multiplier") is not None or item.get("income_required_eur") is not None:
        return item
    blob = " ".join(
        p for p in (item.get("title"), item.get("location"), item.get("notes")) if p
    )
    fields = extract_income_requirement(blob, rent_eur=item.get("rent_eur"))
    if not fields:
        return item
    return {**item, **fields}


def _ensure_neighborhood(item: dict) -> dict:
    wijk = resolve_neighborhood(
        item.get("title") or "",
        item.get("location") or "",
        item.get("notes") or "",
        geocode_wijk=item.get("neighborhood") or "",
    )
    if wijk and wijk != item.get("neighborhood"):
        return {**item, "neighborhood": wijk}
    if not item.get("neighborhood"):
        return {**item, "neighborhood": wijk}
    return item


def _maybe_enrich(listing):
    if scan_profile() == "fast":
        if listing.rent_eur is not None and listing.size_m2 is not None:
            return attach_income_requirement(listing)
    needs_fields = listing.rent_eur is None or listing.size_m2 is None
    if (
        not needs_fields
        and listing.notes
        and len(listing.notes) > 250
        and listing.platform_listed_date
    ):
        return listing
    if not needs_fields and listing.notes and len(listing.notes) > 800:
        return listing
    enriched = enrich_listing(listing)
    if needs_fields and (enriched.rent_eur is None or enriched.size_m2 is None):
        enriched = maybe_llm_fill_listing(enriched)
    return enriched


def _sort_newest_first(item: dict) -> tuple:
    raw = item.get("first_seen_utc") or ""
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        ts = 0.0
    listed = item.get("platform_listed_date") or ""
    return (-ts, listed, not item.get("is_new_today", False))


def _load_application_status() -> dict:
    path = Path("data/application_status.json")
    if not path.exists():
        return {
            "reacties_verstuurd": "180+",
            "bezichtigingen": 2,
            "kijkavonden": 2,
            "rejections": 86,
            "no_response": 4,
            "rejected_addresses": ["PSV-laan 233", "Schootsestraat 94 A"],
            "sociale_huur": {
                "platform": "Wooniezie",
                "inschrijfduur": "4 jaar en 5 maanden",
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
        "directwonen": "DirectWonen",
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


if __name__ == "__main__":
    result = run_workrun()
    print(f"Generated {len(result['listings'])} listing(s) from {len(result['provider_results'])} provider(s).")
