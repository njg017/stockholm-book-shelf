"""Fetch and normalise book records from Stockholms stadsbibliotek.

This is a scaffold. Replace `fetch_catalogue_page` with the real catalogue
endpoint or parsing strategy once its response format has been validated.

Design principles:
- Fetch respectfully and cache results.
- Never assume availability is live; retain an `updated_at` timestamp.
- Keep raw source data separate from the cleaned site data.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"


def fetch_catalogue_page(query: str, page: int = 1) -> dict[str, Any]:
    """Return a normalised page of catalogue results.

    TODO: implement against the actual Stockholms stadsbibliotek catalogue.
    The returned structure should be stable regardless of the underlying
    HTML, JSON or API response.
    """
    raise NotImplementedError(
        "Implement the real catalogue request after inspecting the search response."
    )


def normalise_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw catalogue record into the site data model."""
    return {
        "id": raw.get("isbn") or raw.get("record_id"),
        "title": raw.get("title", "").strip(),
        "author": raw.get("author", "").strip(),
        "isbn": raw.get("isbn"),
        "language": raw.get("language"),
        "format": raw.get("format", "book"),
        "genres": raw.get("genres", []),
        "subjects": raw.get("subjects", []),
        "published_year": raw.get("published_year"),
        "library": {
            "available_branches": raw.get("available_branches", []),
            "total_copies": raw.get("total_copies"),
            "available_copies": raw.get("available_copies"),
            "reservation_url": raw.get("reservation_url"),
        },
        "shelves": [],
        "added_at": time.strftime("%Y-%m-%d"),
    }


def save_raw(records: list[dict[str, Any]], filename: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / filename
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    print("Scaffold ready. Implement fetch_catalogue_page next.")
