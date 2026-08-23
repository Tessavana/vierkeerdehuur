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

# Home-swap / trade listings — almost never useful when searching for a normal rental.
WONINGRUIL_MARKERS = (
    "woningruil",
    "woning ruil",
    "huisruil",
    "huis ruil",
    "ruilwoning",
    "te ruil",
    "ruil woning",
    "home swap",
    "homeswap",
    "house swap",
    "apartment swap",
)

_ALLOWED_CITIES = ("eindhoven", "veldhoven")
_REJECTED_MUNICIPALITIES = (
    "waalre",
    "geldrop",
    "geldrop-mierlo",
    "best",
    "helmond",
    "nuenen",
    "son en breugel",
    "valkenswaard",
    "hertogenbosch",
    "'s-hertogenbosch",
    "den bosch",
    "tilburg",
    "boxtel",
    "oisterwijk",
    "roermond",
    "asten",
    "deurne",
    "someren",
    "laarbeek",
    "heeze-leende",
)

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
    "studentenhuis",
    "studenten huis",
    "huisvesting voor studenten",
    "geschikt voor studenten",
    "alleen geschikt voor student",
    "niet geschikt voor werkenden",
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


_OUTDOOR_YES = ("balkon", "tuin", "terras", "dakterras", "buitenruimte")
_OUTDOOR_NO = (
    "geen balkon",
    "geen tuin",
    "geen terras",
    "zonder buitenruimte",
    "geen buitenruimte",
    "no balcony",
    "no garden",
)


def detect_outdoor(text: str) -> tuple[bool, bool]:
    """Return (known, has_outdoor) from listing text."""
    blob = (text or "").lower()
    if not blob.strip():
        return False, False
    if any(p in blob for p in _OUTDOOR_NO):
        return True, False
    if any(k in blob for k in _OUTDOOR_YES):
        return True, True
    return False, False


def _search_blob(listing: Listing) -> str:
    parts = [listing.title, listing.location, listing.url]
    if listing.notes:
        parts.append(listing.notes[:4000])
    return " ".join(parts).lower()


def _in_allowed_city(searchable: str) -> tuple[bool, str]:
    if any(city in searchable for city in _REJECTED_MUNICIPALITIES):
        return False, "outside_city"
    if "eindhoven" in searchable or "veldhoven" in searchable:
        return True, "ok"
    return False, "outside_city"


def _is_north_eindhoven(searchable: str) -> bool:
    if "noord-brabant" in searchable:
        return False
    north_markers = (
        "eindhoven-noord",
        "eindhoven noord",
        "woensel-noord",
        "woensel noord",
        " noord,",
        " noord ",
    )
    return any(m in searchable for m in north_markers)


def is_rental_match(listing: Listing, config: AppConfig) -> bool:
    ok, _reason = evaluate_rental(listing, config)
    return ok


def evaluate_rental(listing: Listing, config: AppConfig) -> tuple[bool, str]:
    from src.listing_detail import restriction_reason_from_listing

    extra = restriction_reason_from_listing(listing)
    if extra:
        return False, extra

    searchable = _search_blob(listing)
    # Keep the shortlist actionable: require concrete rent/size data.
    if listing.rent_eur is None or listing.size_m2 is None:
        return False, "missing_data"
    if listing.rent_eur < 300:
        return False, "invalid_price"
    if any(marker in searchable for marker in INACTIVE_LISTING_MARKERS):
        return False, "inactive_listing"
    if any(marker in searchable for marker in WONINGRUIL_MARKERS):
        return False, "woningruil"
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
    ok_city, city_reason = _in_allowed_city(searchable)
    if not ok_city:
        return False, city_reason
    if _is_north_eindhoven(searchable):
        return False, "north_eindhoven"
    if "blauwe loper" in searchable:
        return False, "student_area"
    return True, "ok"


def _size_score(size_m2: int | None, min_size: int) -> int:
    """Reward larger flats above the hard minimum (m²)."""
    if size_m2 is None:
        return 0
    if size_m2 >= min_size + 25:
        return 20
    if size_m2 >= min_size + 15:
        return 15
    if size_m2 >= min_size + 8:
        return 10
    if size_m2 >= min_size:
        return 5
    return 0


def score_rental(listing: Listing, config: AppConfig) -> int:
    score = 0
    searchable = _search_blob(listing)
    if "strijp" in searchable:
        score += 25
    if any(area in searchable for area in PREFERRED_NEIGHBORHOODS):
        score += 20
    if listing.rent_eur is not None and listing.rent_eur <= config.max_rent:
        score += 15
    score += _size_score(listing.size_m2, config.min_size)
    if listing.outdoor_space:
        score += 15
    if _is_north_eindhoven(searchable):
        score -= 40
    return score
