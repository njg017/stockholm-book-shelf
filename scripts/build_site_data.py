"""Build the final JSON data files consumed by the static front end.

Input: data/raw/*.json
Output: data/books.json and data/shelves.json
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"

SHELVES = [
    {"id": "new", "title": "Nya på biblioteket"},
    {"id": "popular", "title": "Populära just nu"},
    {"id": "english-fiction", "title": "Engelsk skönlitteratur"},
    {"id": "swedish-fiction", "title": "Svensk skönlitteratur"},
    {"id": "crime", "title": "Crime & thriller"},
    {"id": "scifi-fantasy", "title": "Sci-fi & fantasy"},
    {"id": "children", "title": "För barn & familjen"},
]


def build_shelves(books: list[dict]) -> dict[str, list[dict]]:
    shelves: dict[str, list[dict]] = {shelf["id"]: [] for shelf in SHELVES}

    for book in books:
        for shelf_id in book.get("shelves", []):
            if shelf_id in shelves:
                shelves[shelf_id].append(book)

    return shelves


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raw_files = sorted(RAW_DIR.glob("*.json")) if RAW_DIR.exists() else []
    books: list[dict] = []

    for path in raw_files:
        books.extend(json.loads(path.read_text(encoding="utf-8")))

    write_json(DATA_DIR / "books.json", books)
    write_json(DATA_DIR / "shelves.json", build_shelves(books))
    print(f"Built site data from {len(books)} books.")
