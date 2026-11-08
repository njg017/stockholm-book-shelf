"""End-to-end importer for Bokhyllan Stockholm.

Pipeline:

1. Read structured search seeds from config/seeds.json
2. Search Stockholms stadsbibliotek for matching title IDs
3. Fetch each unique title page
4. Extract richer metadata and holdings
5. Enrich records through Open Library where ISBNs are available
6. De-duplicate records and assign shelves
7. Write data/books.json, data/shelves.json and data/import-report.json

A title page can contain multiple formats and copies. This importer treats
`title_id` as the library work identifier and preserves holdings in the record.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from stockholm_library import LibraryClient, LibrarySearchError
from enrich_openlibrary import enrich_record

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "seeds.json"
DATA_DIR = ROOT / "data"

SHELF_RULES = {
    "english-fiction": lambda book: str(book.get("language", "")).lower().startswith("en"),
    "swedish-fiction": lambda book: str(book.get("language", "")).lower().startswith("sv"),
    "crime": lambda book: any(
        term in " ".join(book.get("subjects", [])).lower()
        for term in ("crime", "thriller", "mystery", "deckare", "krimi")
    ),
    "scifi-fantasy": lambda book: any(
        term in " ".join(book.get("subjects", [])).lower()
        for term in ("science fiction", "fantasy", "sci-fi", "fantasy")
    ),
    "children": lambda book: any(
        term in " ".join(book.get("subjects", [])).lower()
        for term in ("children", "barn", "young adult", "ungdom", "bilderbok")
    ),
}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing configuration: {path}")

    config = json.loads(path.read_text(encoding="utf-8"))
    if not config.get("seeds"):
        raise ValueError("config/seeds.json must contain a non-empty 'seeds' array")

    return config


def deduplicate(books: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate primarily by library title ID, then ISBN/title."""
    by_key: dict[str, dict[str, Any]] = {}

    for book in books:
        title_id = str(book.get("title_id") or "")
        isbn = book.get("isbn")
        title = (book.get("title") or "").strip().lower()

        if title_id:
            key = f"title:{title_id}"
        elif isbn:
            key = f"isbn:{isbn}"
        elif title:
            key = f"title-text:{title}"
        else:
            continue

        existing = by_key.get(key)
        if existing is None:
            by_key[key] = book
            continue

        existing["shelves"] = sorted(
            set(existing.get("shelves", []) + book.get("shelves", []))
        )

        # Keep the record with the most holdings information.
        if len(book.get("holdings", [])) > len(existing.get("holdings", [])):
            existing["holdings"] = book["holdings"]
            existing["available_branches"] = book.get("available_branches", [])
            existing["available_copies"] = book.get("available_copies", 0)
            existing["total_copies"] = book.get("total_copies", 0)

    return list(by_key.values())


def assign_shelves(book: dict[str, Any]) -> list[str]:
    shelves = set(book.get("shelves", []))

    if book.get("available_copies", 0):
        shelves.add("available-now")

    for shelf_id, matches in SHELF_RULES.items():
        try:
            if matches(book):
                shelves.add(shelf_id)
        except Exception:
            continue

    return sorted(shelves)


def import_library(
    max_titles_per_seed: int = 20,
    enrich: bool = True,
    request_delay: float = 1.5,
) -> dict[str, Any]:
    config = load_config()
    client = LibraryClient(request_delay=request_delay)

    collected: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    title_ids_seen: set[str] = set()

    for seed in config["seeds"]:
        author = seed.get("author")
        isbn = seed.get("isbn")
        query = seed.get("query")
        branch = seed.get("branch")
        shelf = seed.get("shelf", "new")

        if not any((author, isbn, query, branch)):
            errors.append({"seed": json.dumps(seed), "error": "Seed has no search criteria"})
            continue

        try:
            title_refs = client.search_titles(
                query=query,
                author=author,
                isbn=isbn,
                branch=branch,
            )[:max_titles_per_seed]
        except Exception as exc:
            errors.append(
                {
                    "seed": author or isbn or query or branch or "unknown",
                    "error": f"Search failed: {exc}",
                }
            )
            continue

        for reference in title_refs:
            title_id = reference["title_id"]
            if title_id in title_ids_seen:
                continue
            title_ids_seen.add(title_id)

            try:
                book = client.get_title(title_id)
                book["shelves"] = [shelf]
                collected.append(book)
            except Exception as exc:
                errors.append(
                    {
                        "seed": author or isbn or query or branch or "unknown",
                        "title_id": title_id,
                        "error": f"Title fetch failed: {exc}",
                    }
                )

    if enrich:
        for book in collected:
            try:
                enrich_record(book)
            except Exception as exc:
                errors.append(
                    {
                        "title_id": book.get("title_id", "unknown"),
                        "error": f"Open Library enrichment failed: {exc}",
                    }
                )

    books = deduplicate(collected)
    for book in books:
        book["shelves"] = assign_shelves(book)
        book["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    shelves: dict[str, list[dict[str, Any]]] = {}
    for book in books:
        for shelf_id in book["shelves"]:
            shelves.setdefault(shelf_id, []).append(book)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "books.json").write_text(
        json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA_DIR / "shelves.json").write_text(
        json.dumps(shelves, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seed_count": len(config["seeds"]),
        "unique_title_count": len(books),
        "error_count": len(errors),
        "errors": errors,
    }
    (DATA_DIR / "import-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import books from Stockholms stadsbibliotek")
    parser.add_argument("--max-titles", type=int, default=20)
    parser.add_argument("--no-enrich", action="store_true")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    report = import_library(
        max_titles_per_seed=args.max_titles,
        enrich=not args.no_enrich,
        request_delay=args.delay,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
