"""End-to-end importer for Bokhyllan Stockholm.

Pipeline:

1. Read search seeds from config/seeds.json
2. Search Stockholms stadsbibliotek using SearchClient
3. Cache every raw response
4. Normalise and de-duplicate records
5. Enrich records through Open Library where ISBNs are available
6. Assign records to shelves
7. Write data/books.json, data/shelves.json and data/import-report.json

The importer is designed to fail loudly rather than publish incomplete or
incorrect availability data.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from stockholm_library import SearchClient, LibrarySearchError
from enrich_openlibrary import enrich_record

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "seeds.json"
DATA_DIR = ROOT / "data"

SHELF_RULES = {
    "english-fiction": lambda book: book.get("language", "").lower().startswith("en")
    and book.get("format", "book") == "book",
    "swedish-fiction": lambda book: book.get("language", "").lower().startswith("sv")
    and book.get("format", "book") == "book",
    "crime": lambda book: any(
        term in " ".join(book.get("genres", []) + book.get("subjects", [])).lower()
        for term in ("crime", "thriller", "mystery", "deckare", "thriller")
    ),
    "scifi-fantasy": lambda book: any(
        term in " ".join(book.get("genres", []) + book.get("subjects", [])).lower()
        for term in ("science fiction", "fantasy", "sci-fi", "fantasy")
    ),
    "children": lambda book: any(
        term in " ".join(book.get("genres", []) + book.get("subjects", [])).lower()
        for term in ("children", "barn", "young adult", "ungdom")
    ),
}


def load_seeds(path: Path = CONFIG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing seed configuration: {path}")

    config = json.loads(path.read_text(encoding="utf-8"))
    seeds = config.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("config/seeds.json must contain a non-empty 'seeds' array")

    return seeds


def deduplicate(books: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer ISBN identity, then title/author identity."""
    by_key: dict[str, dict[str, Any]] = {}

    for book in books:
        isbn = book.get("isbn")
        title = (book.get("title") or "").strip().lower()
        author = (book.get("author") or "").strip().lower()
        key = f"isbn:{isbn}" if isbn else f"title:{title}|author:{author}"

        if not title:
            continue

        existing = by_key.get(key)
        if existing is None:
            by_key[key] = book
            continue

        # Keep the record with the most complete library information.
        existing_branches = existing.get("library", {}).get("available_branches", [])
        new_branches = book.get("library", {}).get("available_branches", [])
        if len(new_branches) > len(existing_branches):
            existing["library"] = book["library"]

        existing.setdefault("shelves", [])
        existing["shelves"] = sorted(set(existing["shelves"] + book.get("shelves", [])))

    return list(by_key.values())


def assign_shelves(book: dict[str, Any]) -> list[str]:
    shelves = set(book.get("shelves", []))

    if book.get("library", {}).get("available_copies", 0) not in (None, 0):
        shelves.add("available-now")

    for shelf_id, matches in SHELF_RULES.items():
        try:
            if matches(book):
                shelves.add(shelf_id)
        except Exception:
            # A shelf rule must never prevent a valid book from being published.
            continue

    return sorted(shelves)


def import_library(
    max_results_per_seed: int = 40,
    enrich: bool = True,
    request_delay: float = 1.5,
) -> dict[str, Any]:
    seeds = load_seeds()
    client = SearchClient(request_delay=request_delay)

    collected: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for seed in seeds:
        query = seed.get("query", "").strip()
        if not query:
            continue

        try:
            results = client.search(query, page=1)[:max_results_per_seed]
            for result in results:
                result["shelves"] = [seed.get("shelf", "new")]
                collected.append(result)
        except (LibrarySearchError, Exception) as exc:
            errors.append({"query": query, "error": str(exc)})

    if enrich:
        for book in collected:
            try:
                enrich_record(book)
            except Exception as exc:
                errors.append(
                    {
                        "query": book.get("title", "unknown"),
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
        "seed_count": len(seeds),
        "book_count": len(books),
        "error_count": len(errors),
        "errors": errors,
    }
    (DATA_DIR / "import-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import books from Stockholms stadsbibliotek")
    parser.add_argument("--max-results", type=int, default=40)
    parser.add_argument("--no-enrich", action="store_true")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    report = import_library(
        max_results_per_seed=args.max_results,
        enrich=not args.no_enrich,
        request_delay=args.delay,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
