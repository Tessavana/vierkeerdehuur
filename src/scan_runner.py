"""Parallel provider fetch with per-provider timeout and global time budget."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from dataclasses import dataclass
from typing import Any, Callable


def scan_time_budget_seconds() -> float:
    raw = os.getenv("SCAN_TIME_BUDGET_SECONDS", "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def provider_timeout_seconds() -> float:
    return float(os.getenv("SCAN_PROVIDER_TIMEOUT_SECONDS", "90"))


def parallel_workers() -> int:
    return max(1, int(os.getenv("SCAN_PARALLEL_WORKERS", "4")))


@dataclass
class ScanClock:
    budget_seconds: float

    def __post_init__(self) -> None:
        self._start = time.monotonic()

    def expired(self) -> bool:
        if self.budget_seconds <= 0:
            return False
        return (time.monotonic() - self._start) >= self.budget_seconds

    def elapsed(self) -> float:
        return time.monotonic() - self._start


ProviderFn = Callable[[Any], dict[str, Any]]


def run_live_providers_parallel(
    jobs: list[tuple[Any, ProviderFn]],
    *,
    clock: ScanClock | None = None,
) -> list[dict[str, Any]]:
    """Run provider jobs concurrently. Each job returns a provider_results-style dict."""
    if not jobs:
        return []
    if clock and clock.expired():
        print("scan: time budget exhausted before live fetches")
        return [
            {
                "provider": p.__class__.__name__,
                "provider_name": p.__class__.__name__.replace("Provider", ""),
                "status": "skipped_budget",
                "parsed": 0,
                "suitable": 0,
                "excluded": 0,
                "error": "scan time budget exhausted",
            }
            for p, _ in jobs
        ]

    timeout = provider_timeout_seconds()
    workers = min(parallel_workers(), len(jobs))
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fn, provider): provider for provider, fn in jobs}
        for fut in as_completed(future_map, timeout=timeout * len(jobs)):
            provider = future_map[fut]
            name = provider.__class__.__name__
            try:
                results.append(fut.result(timeout=timeout))
            except FuturesTimeout:
                print(f"scan: provider timeout ({name}, {timeout}s)")
                results.append(
                    {
                        "provider": name,
                        "provider_name": name.replace("Provider", ""),
                        "status": "error",
                        "parsed": 0,
                        "suitable": 0,
                        "excluded": 0,
                        "error": f"timeout after {timeout}s",
                    }
                )
            except Exception as exc:
                print(f"scan: provider error ({name}): {exc}")
                results.append(
                    {
                        "provider": name,
                        "provider_name": name.replace("Provider", ""),
                        "status": "error",
                        "parsed": 0,
                        "suitable": 0,
                        "excluded": 0,
                        "error": str(exc),
                    }
                )
    return results
