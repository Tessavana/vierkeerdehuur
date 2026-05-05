from src.config import AppConfig
from src.models import Listing

PREFERRED_NEIGHBORHOODS = {
    "strijp",
    "centrum",
    "bergen",
    "vonderkwartier",
    "engelsbergen",
    "schrijversbuurt",
}

BLOCKED_KEYWORDS = {"student", "anti-kraak", "antikraak", "temporary", "tijdelijk"}


def is_rental_match(listing: Listing, config: AppConfig) -> bool:
    ok, _reason = evaluate_rental(listing, config)
    return ok


def evaluate_rental(listing: Listing, config: AppConfig) -> tuple[bool, str]:
    searchable = f"{listing.title} {listing.location}".lower()
    # Keep the shortlist actionable: require concrete rent/size data.
    if listing.rent_eur is None or listing.size_m2 is None:
        return False, "missing_data"
    if listing.rent_eur < 300:
        return False, "invalid_price"
    if any(word in searchable for word in BLOCKED_KEYWORDS):
        return False, "blocked_keyword"
    if listing.rent_eur > config.max_rent:
        return False, "above_budget"
    if listing.size_m2 < config.min_size:
        return False, "too_small"
    if "eindhoven" not in searchable:
        return False, "outside_city"
    if "noord" in searchable:
        return False, "north_eindhoven"
    return True, "ok"


def score_rental(listing: Listing, config: AppConfig) -> int:
    score = 0
    searchable = f"{listing.title} {listing.location}".lower()
    if "strijp" in searchable:
        score += 25
    if any(area in searchable for area in PREFERRED_NEIGHBORHOODS):
        score += 20
    if listing.rent_eur is not None and listing.rent_eur <= config.max_rent:
        score += 15
    if listing.outdoor_space:
        score += 15
    if "noord" in searchable:
        score -= 40
    return score
