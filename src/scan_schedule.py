"""Incremental scan tiers: express (fast CI) vs deep (Playwright rotation)."""

import os

NUM_PROVIDER_GROUPS = 3

# HTTP/API — live every express run.
_EXPRESS_ALWAYS_LIVE = frozenset(
    {
        "VbtProvider",
        "RentfinderProvider",
        "RotsvastProvider",
        "KamernetProvider",
        "HuislijnProvider",
    }
)

# Playwright-heavy — cache-only on express; rotated on deep runs.
_EXPRESS_CACHE_ONLY = frozenset(
    {
        "FundaProvider",
        "NmgProvider",
        "VestedaProvider",
        "HuurwoningenProvider",
        "ParariusProvider",
    }
)

_FAST_ROTATE_PROVIDERS: dict[str, int] = {
    "HuurwoningenProvider": 6,
    "ParariusProvider": 3,
    "DirectWonenProvider": 4,
    "FundaProvider": 4,
    "NmgProvider": 6,
    "VestedaProvider": 6,
}

_PROVIDER_PHASE: dict[str, int] = {
    "ParariusProvider": 0,
    "FundaProvider": 0,
    "KamernetProvider": 0,
    "HuislijnProvider": 0,
    "RotsvastProvider": 0,
    "NmgProvider": 0,
    "VbtProvider": 1,
    "RentfinderProvider": 1,
    "DirectWonenProvider": 1,
    "VestedaProvider": 2,
    "HuurwoningenProvider": 2,
}


def scan_profile() -> str:
    return os.getenv("SCAN_PROFILE", "full").strip().lower()


def scan_tier() -> str:
    raw = os.getenv("SCAN_TIER", "").strip().lower()
    if raw in {"express", "deep"}:
        return raw
    return "express" if scan_profile() == "fast" else "deep"


def bundle_enabled() -> bool:
    """Fast/express runs rely on the bundle for cache-only providers."""
    if scan_profile() == "fast":
        return True
    return os.getenv("INCREMENTAL_SCAN", "false").strip().lower() in {"1", "true", "yes", "on"}


def incremental_scan_enabled() -> bool:
    return bundle_enabled()


def scan_rotation_modulus() -> int:
    if scan_profile() == "fast":
        return 1
    raw = os.getenv("SCAN_ROTATION", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _github_run_number() -> int:
    raw = os.getenv("GITHUB_RUN_NUMBER", "0").strip()
    try:
        return int(raw)
    except ValueError:
        return 0


def _fast_rotate_live(class_name: str) -> bool:
    period = _FAST_ROTATE_PROVIDERS.get(class_name)
    if period is None:
        return True
    return _github_run_number() % period == 0


def current_phase() -> int | None:
    if scan_tier() == "express":
        return None
    if not incremental_scan_enabled():
        return None
    mod = scan_rotation_modulus()
    if mod <= 1:
        mod = NUM_PROVIDER_GROUPS
    return _github_run_number() % mod


def provider_should_fetch_live(class_name: str) -> bool:
    if class_name == "JsonFileProvider":
        return True

    tier = scan_tier()

    if tier == "express":
        if class_name in _EXPRESS_CACHE_ONLY:
            return False
        if class_name in _EXPRESS_ALWAYS_LIVE:
            return True
        return _fast_rotate_live(class_name)

    # deep tier: rotate Playwright providers; always refresh HTTP sources.
    if class_name in _EXPRESS_ALWAYS_LIVE:
        return True
    if class_name in _EXPRESS_CACHE_ONLY:
        return _fast_rotate_live(class_name)
    return _fast_rotate_live(class_name)


def filter_providers_for_incremental(providers: list) -> list:
    return [p for p in providers if provider_should_fetch_live(p.__class__.__name__)]
