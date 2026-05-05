"""Incremental scan: rotate heavy providers across scheduled runs to reduce compute."""

import os

NUM_PROVIDER_GROUPS = 3

# Which fetch group (0..NUM_PROVIDER_GROUPS-1) each provider belongs to.
_PROVIDER_PHASE: dict[str, int] = {
    "ParariusProvider": 0,
    "FundaProvider": 0,
    "KamernetProvider": 0,
    "HuislijnProvider": 0,
    "VbtProvider": 1,
    "RentfinderProvider": 1,
    "VestedaProvider": 2,
    "HuurwoningenProvider": 2,
}


def incremental_scan_enabled() -> bool:
    return os.getenv("INCREMENTAL_SCAN", "false").strip().lower() in {"1", "true", "yes", "on"}


def scan_rotation_modulus() -> int:
    raw = os.getenv("SCAN_ROTATION", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def current_phase() -> int | None:
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
    phase = current_phase()
    if phase is None:
        return True
    if class_name == "JsonFileProvider":
        return True
    group = _PROVIDER_PHASE.get(class_name, 0)
    return group == (phase % NUM_PROVIDER_GROUPS)


def filter_providers_for_incremental(providers: list) -> list:
    return [p for p in providers if provider_should_fetch_live(p.__class__.__name__)]
