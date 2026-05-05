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

# No longer on the market / closed intake (Dutch + English fragments).
INACTIVE_LISTING_MARKERS = (
    "niet meer beschikbaar",
    "niet langer beschikbaar",
    "reeds verhuurd",
    "is verhuurd",
    "woning is verhuurd",
    "deze woning is verhuurd",
    "definitief verhuurd",
    "aanmelding gesloten",
    "inschrijving gesloten",
    "inschrijvingen gesloten",
    "geen inschrijvingen meer",
    "reactietermijn gesloten",
    "reactieperiode gesloten",
    "momenteel 0 woning",
    "0 woning(en) beschikbaar",
    "archief",
    "verlopen aanbod",
    "no longer available",
    "not available anymore",
)

# Student-only or clearly student housing.
STUDENT_ONLY_MARKERS = (
    "studentenwoning",
    "studentenwoningen",
    "uitsluitend student",
    "uitsluitend voor studenten",
    "alleen voor studenten",
    "alleen studenten",
    "only for students",
    "only students",
    "studentenkamer",
    "studenten complex",
    "studentencomplex",
    "kamer voor studenten",
    "huurder moet student",
    "inschrijving alleen student",
)

# “Max X years in NL” / newcomer-only schemes.
NEWCOMER_RESTRICTION_MARKERS = (
    "maximaal 1 jaar in nederland",
    "maximum 1 year in the netherlands",
    "max 1 jaar in nederland",
    "maximaal één jaar in nederland",
    "maximaal een jaar in nederland",
    "niet langer dan 1 jaar woonachtig",
    "niet langer dan één jaar woonachtig",
    "woonverleden in nederland max",
    "woonverleden in nederland: max",
    "kennismigrant",
    "kennis migrant",
    "alleen voor kennismigrant",
    "nieuwkomersregeling",
    "huisvesting nieuwkomers",
    "maximaal 1 jaar woonachtig",
    "max. 1 jaar in nl",
)


def _search_blob(listing: Listing) -> str:
    parts = [listing.title, listing.location]
    if listing.notes:
        parts.append(listing.notes)
    return " ".join(parts).lower()


def is_rental_match(listing: Listing, config: AppConfig) -> bool:
    ok, _reason = evaluate_rental(listing, config)
    return ok


def evaluate_rental(listing: Listing, config: AppConfig) -> tuple[bool, str]:
    searchable = _search_blob(listing)
    # Keep the shortlist actionable: require concrete rent/size data.
    if listing.rent_eur is None or listing.size_m2 is None:
        return False, "missing_data"
    if listing.rent_eur < 300:
        return False, "invalid_price"
    if any(marker in searchable for marker in INACTIVE_LISTING_MARKERS):
        return False, "inactive_listing"
    if any(marker in searchable for marker in STUDENT_ONLY_MARKERS):
        return False, "student_only"
    if any(marker in searchable for marker in NEWCOMER_RESTRICTION_MARKERS):
        return False, "newcomer_restriction"
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
    searchable = _search_blob(listing)
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
