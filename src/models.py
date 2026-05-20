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
    outdoor_space: bool
    contract_months: Optional[int] = None
    available_from: Optional[str] = None
    notes: Optional[str] = None
    platform_listed_date: Optional[str] = None  # YYYY-MM-DD on source site
