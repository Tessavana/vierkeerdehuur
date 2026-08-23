"""Incremental scan: rotate heavy providers; fast profile for frequent light runs."""

import os

NUM_PROVIDER_GROUPS = 3

# Fast = HTTP/API only (~1–2 min). Heavy = Playwright or many detail pages.
_FAST_PROVIDERS = frozenset(
    {
        "ParariusProvider",
        "RotsvastProvider",
        "KamernetProvider",
        "HuislijnProvider",
        "RentfinderProvider",
        "VbtProvider",
        "DirectWonenProvider",
        "HuurwoningenProvider",
    }
)
_HEAVY_PROVIDERS = frozenset(
    {
        "FundaProvider",
        "NmgProvider",
        "VestedaProvider",
    }
)

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


def incremental_scan_enabled() -> bool:
    if scan_profile() == "fast":
        return True
    return os.getenv("INCREMENTAL_SCAN", "false").strip().lower() in {"1", "true", "yes", "on"}


def scan_rotation_modulus() -> int:
    if scan_profile() == "fast":
        return 1
    raw = os.getenv("SCAN_ROTATION", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def current_phase() -> int | None:
    if scan_profile() == "fast":
        return None
    if not incremental_scan_enabled():
        return None
    mod = scan_rotation_modulus()
    if mod <= 1:
        return None
    run = os.getenv("GITHUB_RUN_NUMBER", "0").strip()
    try:
        rn = int(run)
    except ValueError:
        rn = 0
    return rn % mod


def provider_should_fetch_live(class_name: str) -> bool:
    if class_name == "JsonFileProvider":
        return True

    profile = scan_profile()
    if profile == "fast":
        if class_name in _HEAVY_PROVIDERS:
            return False
        return True

    phase = current_phase()
    if phase is None:
        return True
    group = _PROVIDER_PHASE.get(class_name, 0)
    return group == (phase % NUM_PROVIDER_GROUPS)


def filter_providers_for_incremental(providers: list) -> list:
    return [p for p in providers if provider_should_fetch_live(p.__class__.__name__)]
