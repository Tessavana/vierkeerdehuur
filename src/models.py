from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Listing:
    source: str
    source_id: str
    title: str
    url: str
    location: str
    rent_eur: Optional[int]
    size_m2: Optional[int]
    outdoor_space: bool = False
    outdoor_known: bool = False
    contract_months: Optional[int] = None
    available_from: Optional[str] = None
    notes: Optional[str] = None
    platform_listed_date: Optional[str] = None  # YYYY-MM-DD on source site
    application_count: Optional[int] = None
    application_count_label: Optional[str] = None  # e.g. "6+"
    income_multiplier: Optional[float] = None  # e.g. 3.0, 3.5, 4.0 × rent
    income_required_eur: Optional[int] = None  # bruto per month
    income_requirement_label: Optional[str] = None  # e.g. "3,5× huur · €4.025"
    map_lat: Optional[float] = None
    map_lon: Optional[float] = None
