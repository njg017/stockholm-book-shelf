"""Enrich normalised library records with Open Library metadata.

Open Library provides public APIs for book discovery and lookup, including
JSON responses. This scaffold matches records by ISBN where possible.

Docs: https://openlibrary.org/developers/api
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

DATA_DIR = Path("data")
OPEN_LIBRARY_API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"


def fetch_open_library_record(isbn: str) -> dict | None:
    """Fetch metadata for one ISBN from Open Library."""
    if not isbn:
        return None

    url = OPEN_LIBRARY_API.format(isbn=isbn)
    try:
        with urlopen(url, timeout=15) as response:
            payload = json.load(response)
    except Exception:
        return None

    record = payload.get(f"ISBN:{isbn}")
    return record or None


def enrich_record(book: dict) -> dict:
    """Add cover, description and subject data where available."""
    isbn = book.get("isbn")
    metadata = fetch_open_library_record(isbn) if isbn else None

    if metadata:
        book["cover_url"] = metadata.get("cover", {}).get("large") or metadata.get("cover", {}).get("medium")
        book["description"] = metadata.get("notes", {}).get("value") or metadata.get("excerpt", {}).get("value")
        book["subjects"] = sorted(
            {
                *(book.get("subjects") or []),
                *(subject.get("name", "") for subject in metadata.get("subjects", []) if subject.get("name")),
            }
        )

    time.sleep(0.2)  # Be considerate to the public API.
    return book


if __name__ == "__main__":
    sample_path = DATA_DIR / "books.sample.json"
    if sample_path.exists():
        books = json.loads(sample_path.read_text(encoding="utf-8"))
        enriched = [enrich_record(book) for book in books]
        print(json.dumps(enriched, ensure_ascii=False, indent=2))
