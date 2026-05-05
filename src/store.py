import sqlite3
from pathlib import Path

from rapidfuzz import fuzz

from src.models import Listing


class ListingStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT NOT NULL,
                    rent_eur INTEGER,
                    size_m2 INTEGER,
                    listing_url TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_source_source_id ON listings(source, source_id)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_listing_url ON listings(listing_url)"
            )

    def is_new_listing(self, listing: Listing) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM listings WHERE source = ? AND source_id = ?",
                (listing.source, listing.source_id),
            ).fetchone()
            if row:
                return False
            if self._has_possible_duplicate(conn, listing):
                return False
            return True

    def save_listing(self, listing: Listing) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO listings (
                    source, source_id, title, location, rent_eur, size_m2, listing_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.source,
                    listing.source_id,
                    listing.title,
                    listing.location,
                    listing.rent_eur,
                    listing.size_m2,
                    listing.url,
                ),
            )

    def _has_possible_duplicate(self, conn: sqlite3.Connection, listing: Listing) -> bool:
        rows = conn.execute(
            "SELECT location, rent_eur, size_m2 FROM listings WHERE rent_eur IS NOT NULL AND size_m2 IS NOT NULL"
        ).fetchall()
        if listing.rent_eur is None or listing.size_m2 is None:
            return False
        for location, rent_eur, size_m2 in rows:
            similar_street = fuzz.ratio((location or "").lower(), listing.location.lower()) > 85
            close_rent = abs((rent_eur or 0) - listing.rent_eur) <= 50
            close_size = abs((size_m2 or 0) - listing.size_m2) <= 5
            if similar_street and close_rent and close_size:
                return True
        return False
