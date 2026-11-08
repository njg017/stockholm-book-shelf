"""Enrich normalised library records with Open Library metadata, with retries."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

DATA_DIR = Path("data")
OPEN_LIBRARY_API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
OPEN_LIBRARY_SEARCH_API = "https://openlibrary.org/search.json?isbn={isbn}&fields=key,ratings_average,ratings_count,first_publish_year&limit=1"

def fetch_json(url, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            with urlopen(url, timeout=15) as response:
                return json.load(response)
        except Exception as exc:
            last_error = exc
            time.sleep(0.5 * (2 ** attempt))
    raise last_error

def fetch_open_library_record(isbn):
    if not isbn:
        return None
    try:
        payload = fetch_json(OPEN_LIBRARY_API.format(isbn=quote(isbn)))
        record = payload.get(f"ISBN:{isbn}")
        return record if isinstance(record, dict) else None
    except Exception:
        return None

def fetch_open_library_work(isbn):
    if not isbn:
        return None
    try:
        documents = fetch_json(OPEN_LIBRARY_SEARCH_API.format(isbn=quote(isbn))).get("docs") or []
        return documents[0] if documents and isinstance(documents[0], dict) else None
    except Exception:
        return None

def text(value):
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        nested = value.get("value")
        return nested.strip() if isinstance(nested, str) and nested.strip() else None
    return None

def enrich_record(book):
    isbn = book.get("isbn")
    metadata = fetch_open_library_record(isbn) if isbn else None
    work = fetch_open_library_work(isbn) if isbn else None
    if metadata:
        cover = metadata.get("cover")
        if isinstance(cover, dict):
            book["cover_url"] = book.get("cover_url") or cover.get("large") or cover.get("medium")
        book["description"] = book.get("description") or text(metadata.get("notes")) or text(metadata.get("excerpt"))
        subjects = list(book.get("subjects") or [])
        for subject in metadata.get("subjects") or []:
            name = subject.get("name") if isinstance(subject, dict) else subject
            if isinstance(name, str) and name.strip():
                subjects.append(name.strip())
        book["subjects"] = sorted(set(subjects))
    if work:
        book["openlibrary_work_id"] = work.get("key")
        average, count = work.get("ratings_average"), work.get("ratings_count")
        if isinstance(average, (int, float)) and average > 0:
            book["openlibrary_rating_average"] = round(float(average), 2)
        if isinstance(count, int) and count >= 0:
            book["openlibrary_rating_count"] = count
        first_year = work.get("first_publish_year")
        if isinstance(first_year, int):
            book["first_published_year"] = first_year
    published_year = book.get("published_year")
    if isinstance(published_year, int):
        book["is_recent_release"] = published_year >= datetime.now(timezone.utc).year - 2
    time.sleep(0.2)
    return book

if __name__ == "__main__":
    sample_path = DATA_DIR / "books.sample.json"
    if sample_path.exists():
        books = json.loads(sample_path.read_text(encoding="utf-8"))
        print(json.dumps([enrich_record(book) for book in books], ensure_ascii=False, indent=2))
