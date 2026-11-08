"""Search client for Stockholms stadsbibliotek.

The public search interface is at:
https://biblioteket.stockholm.se/sok?text=<query>

This client is deliberately defensive:

1. It saves the raw response before parsing.
2. It tries embedded JSON / JSON-LD before relying on HTML selectors.
3. It normalises records into the project's stable data model.
4. It rate-limits requests and identifies itself with a descriptive User-Agent.

The exact underlying response format must be validated from a saved fixture
before relying on any selector in production.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://biblioteket.stockholm.se"
SEARCH_URL = f"{BASE_URL}/sok"
RAW_DIR = Path("data/raw/search")

DEFAULT_HEADERS = {
    "User-Agent": "BokhyllanStockholm/0.1 (+https://github.com/njg017/stockholm-book-shelf)",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}


class LibrarySearchError(RuntimeError):
    """Raised when the catalogue response cannot be parsed reliably."""


@dataclass
class SearchClient:
    """Small, cache-first client for the public library search."""

    session: requests.Session | None = None
    request_delay: float = 1.5
    timeout: float = 20.0
    cache_raw: bool = True
    _last_request_at: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.session = self.session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def search(self, query: str, page: int = 1) -> list[dict[str, Any]]:
        """Search by free text, ISBN, title or author.

        Returns normalised book records. Raw HTML/JSON is cached first so the
        parser can be developed and debugged without repeated live requests.
        """
        if not query.strip():
            return []

        params = {"text": query.strip()}
        if page > 1:
            params["page"] = str(page)

        response = self._get(SEARCH_URL, params=params)
        raw_text = response.text
        content_type = response.headers.get("Content-Type", "")

        if self.cache_raw:
            self._save_raw_response(query, page, response.status_code, content_type, raw_text)

        if response.status_code >= 400:
            raise LibrarySearchError(f"Library search returned HTTP {response.status_code}")

        if "application/json" in content_type:
            payload = self._parse_json(response)
        else:
            payload = self._parse_html(raw_text, base_url=str(response.url))

        records = self._extract_records(payload)
        return [self._normalise(record, str(response.url)) for record in records]

    def _get(self, url: str, params: dict[str, str]) -> requests.Response:
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at and elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        response = self.session.get(url, params=params, timeout=self.timeout)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response

    def _save_raw_response(
        self,
        query: str,
        page: int,
        status_code: int,
        content_type: str,
        body: str,
    ) -> Path:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60] or "search"
        digest = hashlib.sha1(f"{query}|{page}".encode()).hexdigest()[:10]
        path = RAW_DIR / f"{slug}-page{page}-{digest}.json"

        path.write_text(
            json.dumps(
                {
                    "url": SEARCH_URL,
                    "query": query,
                    "page": page,
                    "status_code": status_code,
                    "content_type": content_type,
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "body": body,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def _parse_json(self, response: requests.Response) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:
            raise LibrarySearchError("Search endpoint returned invalid JSON") from exc

    def _parse_html(self, html: str, base_url: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")

        # Common Next.js/Nuxt-style embedded state. This is a candidate location,
        # not an assumption: validate it against a real saved response.
        for selector in ("script#__NEXT_DATA__", "script#__NUXT__", "script[type='application/json']"):
            tag = soup.select_one(selector)
            if tag and tag.string:
                try:
                    return json.loads(tag.string)
                except ValueError:
                    continue

        # JSON-LD is often present for search-result metadata.
        json_ld = [
            json.loads(tag.string)
            for tag in soup.find_all("script", type="application/ld+json")
            if tag.string
        ]
        if json_ld:
            return {"json_ld": json_ld}

        # Final fallback: derive records from result links/cards.
        records: list[dict[str, Any]] = []
        for link in soup.select("a[href*='/post/'], a[href*='/titel/'], a[href*='/record/']"):
            href = link.get("href", "")
            text = " ".join(link.get_text(separator=" ", strip=True).split())
            if not text:
                continue

            records.append(
                {
                    "title": text,
                    "detail_url": urljoin(base_url, href),
                }
            )

        if not records:
            raise LibrarySearchError(
                "Could not find embedded JSON, JSON-LD or result links. "
                "Inspect the newest file in data/raw/search/ and update the parser."
            )

        return {"records": records}

    def _extract_records(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Locate a result array without assuming one fixed API shape."""

        def walk(value: Any) -> list[dict[str, Any]]:
            found: list[dict[str, Any]] = []
            if isinstance(value, list):
                for item in value:
                    found.extend(walk(item))
            elif isinstance(value, dict):
                if any(key in value for key in ("title", "titel", "name")):
                    found.append(value)
                for child in value.values():
                    found.extend(walk(child))
            return found

        records = walk(payload)

        # Remove obvious duplicates while preserving order.
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in records:
            key = json.dumps(record, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                unique.append(record)
        return unique

    def _normalise(self, record: dict[str, Any], source_url: str) -> dict[str, Any]:
        title = self._first(
            record,
            ("title", "titel", "name"),
            default="",
        )
        author = self._first(
            record,
            ("author", "authors", "forfattare", "författare", "creator"),
            default="",
        )
        isbn = self._first(record, ("isbn", "isbn13", "isbn10"), default=None)

        return {
            "id": isbn or self._first(record, ("id", "record_id", "identifier"), default=None),
            "title": title,
            "author": author,
            "isbn": isbn,
            "language": self._first(record, ("language", "sprak", "språk"), default=None),
            "format": self._first(record, ("format", "mediatype", "media_type"), default="book"),
            "published_year": self._first(record, ("published_year", "year", "ar", "år"), default=None),
            "cover_url": self._first(record, ("cover_url", "cover", "image", "thumbnail"), default=None),
            "detail_url": self._first(record, ("detail_url", "url", "link"), default=source_url),
            "raw_record": record,
            "source_url": source_url,
        }

    @staticmethod
    def _first(record: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", []):
                return value
        return default


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Search Stockholms stadsbibliotek")
    parser.add_argument("query", help="Title, author, subject or ISBN")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--output", default="data/search-results.json")
    args = parser.parse_args()

    client = SearchClient()
    results = client.search(args.query, page=args.page)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(results)} normalised results to {output}")


if __name__ == "__main__":
    main()
