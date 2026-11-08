"""Offline tests for the Stockholm library search client.

Run with:

    python scripts/test_search_client.py

These tests do not contact the live library site. They verify that the client
normalises representative record shapes and raises a useful error when no
recognisable result structure is present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stockholm_library import SearchClient, LibrarySearchError  # noqa: E402


def test_normalises_embedded_json_record() -> None:
    client = SearchClient(cache_raw=False)
    record = {
        "title": "Tomorrow, and Tomorrow, and Tomorrow",
        "author": [{"name": "Gabrielle Zevin"}],
        "isbn": "9780571364886",
        "language": "English",
        "year": 2022,
        "cover": "https://example.com/cover.jpg",
    }

    normalised = client._normalise(record, "https://biblioteket.stockholm.se/sok")

    assert normalised["title"] == "Tomorrow, and Tomorrow, and Tomorrow"
    assert normalised["isbn"] == "9780571364886"
    assert normalised["published_year"] == 2022
    assert normalised["cover_url"] == "https://example.com/cover.jpg"


def test_extracts_records_from_nested_payload() -> None:
    client = SearchClient(cache_raw=False)
    payload = {
        "data": {
            "results": [
                {"title": "Book A", "author": "Author A"},
                {"titel": "Book B", "forfattare": "Author B"},
            ]
        }
    }

    records = client._extract_records(payload)

    assert len(records) == 2
    assert records[0]["title"] == "Book A"
    assert records[1]["titel"] == "Book B"


def test_raises_when_no_results_can_be_identified() -> None:
    client = SearchClient(cache_raw=False)

    try:
        client._extract_records({"unexpected": {"value": 1}})
    except LibrarySearchError:
        pass
    else:
        raise AssertionError("Expected LibrarySearchError")


def test_sample_fixture_is_valid() -> None:
    path = Path(__file__).parent.parent / "data" / "books.sample.json"
    books = json.loads(path.read_text(encoding="utf-8"))

    assert books
    assert all("title" in book and "library" in book for book in books)


if __name__ == "__main__":
    test_normalises_embedded_json_record()
    test_extracts_records_from_nested_payload()
    test_raises_when_no_results_can_be_identified()
    test_sample_fixture_is_valid()
    print("All search-client tests passed.")
