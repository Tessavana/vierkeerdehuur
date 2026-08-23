"""Optional gpt-4o-mini fallback when regex/detail fetch still miss rent or size."""

from __future__ import annotations

import json
import os
import re

from dataclasses import replace

from src.models import Listing


def _llm_mode() -> str:
    explicit = os.getenv("LISTING_LLM_ENABLED", "").strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return "off"
    mode = os.getenv("LISTING_LLM_MODE", "").strip().lower()
    if mode in {"off", "missing_fields"}:
        return mode
    if explicit in {"1", "true", "yes", "on"}:
        return "missing_fields"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "missing_fields"
    return "off"


def maybe_llm_fill_listing(listing: Listing) -> Listing:
    if _llm_mode() != "missing_fields":
        return listing
    if listing.rent_eur is not None and listing.size_m2 is not None:
        return listing
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return listing

    blob = " ".join(
        p for p in (listing.title, listing.location, (listing.notes or "")[:2500]) if p
    )
    if len(blob) < 40:
        return listing

    try:
        import requests
    except ImportError:
        return listing

    model = os.getenv("LISTING_LLM_MODEL", "gpt-4o-mini")
    prompt = (
        "Extract rental listing fields for Eindhoven, Netherlands.\n"
        "Return ONLY valid JSON with keys: rent_eur (int|null), size_m2 (int|null), "
        "location (string|null), student_only (bool).\n"
        "student_only=true only if explicitly for students only.\n\n"
        f"Text:\n{blob[:2800]}"
    )
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 120,
                "temperature": 0,
            },
            timeout=25,
        )
        if r.status_code >= 400:
            return listing
        content = r.json()["choices"][0]["message"]["content"].strip()
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return listing
        data = json.loads(m.group(0))
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError, TypeError, ValueError):
        return listing

    rent = listing.rent_eur
    size = listing.size_m2
    location = listing.location
    notes = listing.notes or ""

    if rent is None and isinstance(data.get("rent_eur"), (int, float)):
        val = int(data["rent_eur"])
        if 200 <= val <= 8000:
            rent = val
    if size is None and isinstance(data.get("size_m2"), (int, float)):
        val = int(data["size_m2"])
        if 10 <= val <= 500:
            size = val
    if location in ("Unknown", "Eindhoven", "") and isinstance(data.get("location"), str):
        loc = data["location"].strip()
        if loc:
            location = loc
    if data.get("student_only") is True and "student_only" not in notes.lower():
        notes = f"{notes} | llm:student_only".strip(" |")

    return replace(listing, rent_eur=rent, size_m2=size, location=location, notes=notes or None)
