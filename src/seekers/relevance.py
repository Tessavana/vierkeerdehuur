"""Relevance scoring for seekers feed (Eindhoven housing). Optional LLM pass."""

from __future__ import annotations

import json
import os
import re
from typing import Any

_AUTO_ACCEPT_SCORE = 90
_BORDERLINE_MIN_SCORE = 55

_STRICT_HOUSING = (
    "huur",
    "huurwoning",
    "woning",
    "appartement",
    "kamer",
    "studio",
    "huis",
    " room",
    "room ",
    "house",
    "apartment",
    "flat",
    "housing",
    "accommodation",
    "accomodation",
    "housemate",
    "huisgenoot",
    "flatmate",
    "woningruil",
    "te huur",
    "for rent",
    "sublet",
    "verhuur",
    "landlord",
    "xior",
    "student housing",
    "huurcontract",
)

_EINDHOVEN_AREA = (
    "eindhoven",
    "strijp",
    "woensel",
    "tongelre",
    "gestel",
    "brainport",
)

# Other places — reject unless Eindhoven is explicitly the target.
_OTHER_PLACES = (
    "lichtenvoorde",
    "roermond",
    "tilburg",
    "amsterdam",
    "rotterdam",
    "utrecht",
    "enschede",
    "den bosch",
    "s-hertogenbosch",
    "breda",
    "geldrop",
    "helmond",
    "valken",
    "best",
    "waalre",
    "nuenen",
    "son en breugel",
    "limburg",
    "groningen",
    "arnhem",
    "nijmegen",
)

_NOISE = (
    "football pitch",
    "hire a football",
    "playing football",
    "metalfans",
    "metal fan",
    "looking for a job",
    "looking for some girl",
    "girls only looking for a gym",
    "gym partner",
    "movement-friendly gym",
    "looking for a movement",
    "looking to make friends",
    "concert vriend",
    "melanie martinez",
    "relatiecoach",
    "mannencirkel",
    "electricien",
    "electrician",
    "electricien",
    "anyone worked at",
    "considering a job",
    "hiring a",
    "dj gezocht",
    "transport verhuizen",
    "beter leren luisteren",
    "bedrijfsschool",
    "how is life/career",
    "master's after",
    "masters after",
    "dutch design week",
    "ddw accomodation",
    "ddw accommodation",
    "during ddw",
    "for one week",
    "one week only",
    "for a month",
    "subletting for a month",
    "exhibited during",
    "reduced rate",
    "prefer to rent it to a woman",
    "prefer to rent to a woman",
    "send me a dm",
    "women only",
    "girls only",
    "scam",
)

_HOUSING_SEEK = (
    "op zoek naar woning",
    "op zoek naar een woning",
    "op zoek naar kamer",
    "op zoek naar appartement",
    "looking for a housemate",
    "looking for housemate",
    "looking for a room",
    "looking for room",
    "looking for an apartment",
    "looking for apartment",
    "looking for housing",
    "looking for accommodation",
    "need a room",
    "need an apartment",
    "dringend op zoek",
    "who can help",
    "wie kan ons helpen",
    "kamer gezocht",
    "woning gezocht",
    "huur gezocht",
    "move to eindhoven",
    "moving to eindhoven",
    "relocating to eindhoven",
    "living at xior",
)


def _has_strict_housing(blob: str) -> bool:
    return any(k in blob for k in _STRICT_HOUSING)


def _mentions_eindhoven(blob: str) -> bool:
    if "eindhoven" in blob:
        return True
    return bool(re.search(r"\b56\d{2}\s?[A-Za-z]{2}\b", blob))


def _is_outside_eindhoven(blob: str) -> bool:
    for place in _OTHER_PLACES:
        if place in blob and not _mentions_eindhoven(blob):
            return True
    if re.search(r"gezocht[^.]{0,40}(lichtenvoorde|roermond|tilburg|geldrop|helmond)", blob):
        return True
    return False


def score_relevance(title: str, snippet: str, *, subreddit: str = "") -> dict[str, Any]:
    blob = f"{title} {snippet}".lower()
    sub = subreddit.lower()

    for noise in _NOISE:
        if noise in blob:
            return {"relevant": False, "score": 0, "reason": f"noise:{noise}"}

    if _is_outside_eindhoven(blob):
        return {"relevant": False, "score": 0, "reason": "outside_eindhoven"}

    if re.search(r"looking for (?:a |an )?(?:job|gym|friend|coach|partner[^h]|electric)", blob):
        return {"relevant": False, "score": 0, "reason": "looking_for_non_housing"}

    has_housing = _has_strict_housing(blob)
    # r/eindhoven helps discovery but still require Eindhoven as housing target.
    has_area = _mentions_eindhoven(blob) or any(a in blob for a in _EINDHOVEN_AREA)
    strong = any(s in blob for s in _HOUSING_SEEK)

    if not has_area:
        return {"relevant": False, "score": 0, "reason": "no_eindhoven_area"}

    if not has_housing and not strong:
        return {"relevant": False, "score": 0, "reason": "no_housing_terms"}

    score = 40
    if strong:
        score += 40
    if has_housing:
        score += 20
    if "eindhoven" in blob:
        score += 10
    if sub == "r/eindhoven":
        score += 5

    return {"relevant": score >= _BORDERLINE_MIN_SCORE, "score": score, "reason": "keyword_match"}


def _llm_mode() -> str:
    """off | borderline | always — borderline is default when OPENAI_API_KEY is set."""
    explicit = os.getenv("SEEKERS_LLM_ENABLED", "").strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return "off"
    mode = os.getenv("SEEKERS_LLM_MODE", "").strip().lower()
    if mode in {"off", "borderline", "always"}:
        return mode
    if explicit in {"1", "true", "yes", "on"}:
        return "always"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "borderline"
    return "off"


def _needs_llm_review(kw: dict[str, Any]) -> bool:
    if not kw["relevant"]:
        return False
    if kw["score"] >= _AUTO_ACCEPT_SCORE:
        return False
    return True


def llm_relevance_check(title: str, snippet: str) -> bool | None:
    """OpenAI check for borderline posts. Returns None if disabled/unavailable."""
    if _llm_mode() == "off":
        return None
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import requests
    except ImportError:
        return None

    model = os.getenv("SEEKERS_LLM_MODEL", "gpt-4o-mini")
    prompt = (
        "You filter posts for a dashboard about HOUSING in Eindhoven, Netherlands.\n"
        "Include: people seeking long-term rooms, apartments, houses, housemates in Eindhoven.\n"
        "Exclude: jobs, gyms, scams, temporary/event stays (DDW), offerings to sublet, "
        "posts outside Eindhoven.\n"
        "Answer ONLY yes or no.\n\n"
        f"Title: {title}\nBody: {snippet[:800]}"
    )
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 5,
                "temperature": 0,
            },
            timeout=20,
        )
        if r.status_code >= 400:
            return None
        answer = r.json()["choices"][0]["message"]["content"].strip().lower()
        return answer.startswith("y")
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError):
        return None


def is_relevant_post(title: str, snippet: str, *, subreddit: str = "", source: str = "") -> bool:
    kw = score_relevance(title, snippet, subreddit=subreddit)
    if not kw["relevant"]:
        return False

    mode = _llm_mode()
    if mode == "off":
        return True
    if mode == "borderline" and not _needs_llm_review(kw):
        return True

    llm = llm_relevance_check(title, snippet)
    if llm is None:
        return True
    return llm
