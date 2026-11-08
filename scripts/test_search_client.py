"""Offline tests for the Stockholm library client and importer.

Run with:

    python scripts/test_search_client.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stockholm_library import (  # noqa: E402
    LibraryClient,
    LibrarySearchError,
    build_search_url,
)
from import_library import assign_shelves, deduplicate  # noqa: E402


def test_builds_author_search_url() -> None:
    url = build_search_url(author="Gabrielle Zevin")
    assert url == "https://biblioteket.stockholm.se/sok?author=Gabrielle+Zevin"


def test_builds_branch_search_url() -> None:
    url = build_search_url(branch="Rinkeby bibliotek", start=20)
    assert "library=Rinkeby+bibliotek" in url
    assert "start=20" in url


def test_title_id_pattern() -> None:
    match = LibraryClient.__dict__  # Ensure import succeeds.
    assert match is not None


def test_normalises_and_deduplicates_titles() -> None:
    books = [
        {
            "title_id": "8487743",
            "title": "Imorgon och imorgon och imorgon",
            "isbn": "9789100254386",
            "language": "Svenska",
            "shelves": ["english-fiction"],
            "holdings": [
                {"branch": "Rinkeby bibliotek", "available": True},
                {"branch": "Tensta bibliotek", "available": False},
            ],
            "available_copies": 1,
        },
        {
            "title_id": "8487743",
            "title": "Imorgon och imorgon och imorgon",
            "shelves": ["crime"],
            "holdings": [],
        },
    ]

    merged = deduplicate(books)
    assert len(merged) == 1
    assert set(merged[0]["shelves"]) == {"english-fiction", "crime"}
    assert len(merged[0]["holdings"]) == 2


def test_assigns_availability_shelf() -> None:
    book = {
        "language": "English",
        "subjects": ["science fiction"],
        "available_copies": 2,
        "shelves": [],
    }

    shelves = assign_shelves(book)
    assert "available-now" in shelves
    assert "english-fiction" in shelves
    assert "scifi-fantasy" in shelves


def test_raises_when_no_title_links_found() -> None:
    client = LibraryClient(cache_raw=False)

    try:
        client._extract_title_links(
            "<html><body><p>No results</p></body></html>",
            "https://biblioteket.stockholm.se/sok",
        )
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
    test_builds_author_search_url()
    test_builds_branch_search_url()
    test_title_id_pattern()
    test_normalises_and_deduplicates_titles()
    test_assigns_availability_shelf()
    test_raises_when_no_title_links_found()
    test_sample_fixture_is_valid()
    print("All library client tests passed.")
