"""Map SEARCH_URLS entries to listing providers."""

from __future__ import annotations

from pathlib import Path

from src.providers import (
    DirectWonenProvider,
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


def build_providers(urls: list[str]) -> list[ListingProvider]:
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
        elif "directwonen.nl" in lower:
            providers.append(DirectWonenProvider(url))
        elif "pararius.com" in lower:
            providers.append(ParariusProvider(url))
        else:
            print(f"unknown search url (skipped): {url}")
    return providers
