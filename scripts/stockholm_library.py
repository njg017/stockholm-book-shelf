"""Search and title client for Stockholms stadsbibliotek.

The public catalogue uses two useful page types:

1. Search results:
   https://biblioteket.stockholm.se/sok?text=&author=Gabrielle%20Zevin

2. Title details:
   https://biblioteket.stockholm.se/titel/8487743

The client follows that two-stage flow:

- `search_titles()` finds title IDs and basic search-result metadata.
- `get_title()` fetches the detailed record for one title ID.

Every response is cached before parsing. The parser is conservative: it will
raise an error rather than invent fields it cannot reliably identify.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://biblioteket.stockholm.se"
SEARCH_URL = f"{BASE_URL}/sok"
TITLE_URL = f"{BASE_URL}/titel"
RAW_DIR = Path("data/raw")

DEFAULT_HEADERS = {
    "User-Agent": "BokhyllanStockholm/0.1 (+https://github.com/njg017/stockholm-book-shelf)",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}

TITLE_ID_PATTERN = re.compile(r"/titel/(\d+)")
ESCAPED_TITLE_ID_PATTERN = re.compile(r"\\/titel\\/(\d+)")


class LibrarySearchError(RuntimeError):
    """Raised when a library response cannot be parsed reliably."""


@dataclass
class LibraryClient:
    """Cache-first client for search results and title pages."""

    session: requests.Session | None = None
    request_delay: float = 1.5
    timeout: float = 20.0
    cache_raw: bool = True
    _last_request_at: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.session = self.session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def search_titles(
        self,
        query: str | None = None,
        author: str | None = None,
        isbn: str | None = None,
        branch: str | None = None,
        start: int = 0,
    ) -> list[dict[str, Any]]:
        """Search the catalogue and return normalised title references."""
        params: dict[str, str] = {}

        if query:
            params["text"] = query.strip()
        if author:
            params["author"] = author.strip()
        if isbn:
            params["text"] = isbn.strip()
        if branch:
            params["library"] = branch.strip()
        if start:
            params["start"] = str(start)

        if not params:
            raise ValueError("Provide at least one of query, author, isbn or branch")

        response = self._get(SEARCH_URL, params=params)
        self._cache_response(
            "search",
            f"{query or author or isbn or ''}|{branch or ''}|{start}",
            response,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        records = self._extract_anchor_records(soup, str(response.url))

        if not records:
            records = self._extract_raw_text_records(response.text)

        if not records:
            raise LibrarySearchError(self._diagnostic_error(response))

        return records

    def get_title(self, title_id: str | int) -> dict[str, Any]:
        """Fetch and parse the detailed record for one library title."""
        title_id = str(title_id).strip()
        if not title_id.isdigit():
            raise ValueError(f"Invalid title ID: {title_id}")

        url = f"{TITLE_URL}/{title_id}"
        response = self._get(url, params={})
        self._cache_response("title", title_id, response)

        soup = BeautifulSoup(response.text, "html.parser")
        title = self._text(soup.select_one("h1"), fallback="")

        if not title:
            raise LibrarySearchError(
                f"Could not identify a title on title page {title_id}. "
                "Inspect the cached response and update the parser."
            )

        record: dict[str, Any] = {
            "title_id": title_id,
            "title": title,
            "title_url": url,
            "author": self._text(
                soup.select_one("[class*='author' i], [data-field*='author' i]"),
                fallback="",
            ),
            "isbn": self._find_labelled_value(soup, ("isbn", "isbn-13", "isbn13")),
            "language": self._find_labelled_value(soup, ("språk", "sprak", "language")),
            "format": self._find_labelled_value(soup, ("mediatyp", "format", "materialtyp")),
            "published_year": self._find_year(soup),
            "description": self._text(
                soup.select_one(
                    "[class*='description' i], [class*='beskrivning' i], meta[name='description']"
                ),
                fallback="",
            ),
            "cover_url": self._cover_url(soup),
            "subjects": self._subjects(soup),
            "holdings": self._holdings(soup),
            "source_url": str(response.url),
        }

        record["available_branches"] = sorted(
            {
                holding["branch"]
                for holding in record["holdings"]
                if holding.get("available")
            }
        )
        record["available_copies"] = sum(
            1 for holding in record["holdings"] if holding.get("available")
        )
        record["total_copies"] = len(record["holdings"])
        record["reservation_url"] = url

        return record

    def _extract_anchor_records(
        self,
        soup: BeautifulSoup,
        source_url: str,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for anchor in soup.select("a[href*='/titel/']"):
            href = anchor.get("href", "")
            match = TITLE_ID_PATTERN.search(href)
            if not match:
                continue

            title_id = match.group(1)
            if title_id in seen_ids:
                continue
            seen_ids.add(title_id)

            card = anchor
            for _ in range(4):
                if card.parent and card.parent.name != "body":
                    card = card.parent

            text = " ".join(card.get_text(separator=" ", strip=True).split())
            records.append(
                {
                    "title_id": title_id,
                    "title_url": urljoin(BASE_URL, f"/titel/{title_id}"),
                    "search_text": text,
                    "source_url": source_url,
                }
            )

        return records

    def _extract_raw_text_records(self, html: str) -> list[dict[str, Any]]:
        """Find title IDs in raw HTML, JSON, escaped JSON and JavaScript.

        Some client-rendered catalogues embed links as escaped JSON, for
        example `\/titel\/8487743`. This fallback finds those IDs without
        assuming that they occur inside an anchor tag.
        """
        ids: list[str] = []

        for pattern in (TITLE_ID_PATTERN, ESCAPED_TITLE_ID_PATTERN):
            ids.extend(match.group(1) for match in pattern.finditer(html))

        # Preserve first-appearance order while removing duplicates.
        unique_ids = list(dict.fromkeys(ids))

        return [
            {
                "title_id": title_id,
                "title_url": f"{TITLE_URL}/{title_id}",
                "search_text": "",
                "source_url": SEARCH_URL,
            }
            for title_id in unique_ids
        ]

    def _diagnostic_error(self, response: requests.Response) -> str:
        body = response.text
        markers = {
            "maintenance": "Underhåll pågår" in body,
            "next_data": "__NEXT_DATA__" in body,
            "nuxt_data": "__NUXT__" in body,
            "json_ld": "application/ld+json" in body,
            "escaped_title": bool(ESCAPED_TITLE_ID_PATTERN.search(body)),
            "plain_title": bool(TITLE_ID_PATTERN.search(body)),
        }

        marker_text = ", ".join(
            f"{name}={value}" for name, value in markers.items()
        )

        return (
            "No title references could be extracted from the search response. "
            f"status={response.status_code}; "
            f"final_url={response.url}; "
            f"content_type={response.headers.get('Content-Type', '')}; "
            f"body_length={len(body)}; "
            f"markers: {marker_text}. "
            "Inspect the newest cached response in data/raw/search/."
        )

    def _get(self, url: str, params: dict[str, str]) -> requests.Response:
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at and elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        response = self.session.get(url, params=params, timeout=self.timeout)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response

    def _cache_response(self, kind: str, key: str, response: requests.Response) -> Path:
        directory = RAW_DIR / kind
        directory.mkdir(parents=True, exist_ok=True)

        slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:80] or "response"
        digest = hashlib.sha1(f"{kind}|{key}|{response.url}".encode()).hexdigest()[:10]
        path = directory / f"{slug}-{digest}.json"

        path.write_text(
            json.dumps(
                {
                    "url": response.url,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("Content-Type", ""),
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "body": response.text,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def _text(self, element: Any, fallback: str = "") -> str:
        if element is None:
            return fallback

        if element.name == "meta":
            return (element.get("content") or fallback).strip()

        return " ".join(element.get_text(separator=" ", strip=True).split()) or fallback

    def _find_labelled_value(self, soup: BeautifulSoup, labels: tuple[str, ...]) -> str:
        normalized_labels = {label.lower() for label in labels}

        for row in soup.select("dt, th, .label, [class*='label' i]"):
            label = self._text(row).rstrip(":").lower()
            if label not in normalized_labels:
                continue

            sibling = row.find_next_sibling()
            value = self._text(sibling)
            if value:
                return value

        for row in soup.select("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = self._text(cells[0]).rstrip(":").lower()
                if label in normalized_labels:
                    return self._text(cells[1])

        return ""

    def _find_year(self, soup: BeautifulSoup) -> int | None:
        value = self._find_labelled_value(
            soup,
            ("utgiven", "utgivningsår", "year", "publicerad"),
        )
        match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", value)
        return int(match.group(1)) if match else None

    def _cover_url(self, soup: BeautifulSoup) -> str:
        image = soup.select_one(
            "img[src*='cover'], img[src*='omslag'], img[alt*='omslag' i], meta[property='og:image']"
        )
        if image is None:
            return ""

        src = image.get("src") or image.get("content") or ""
        return urljoin(str(self.session.headers.get("Referer", BASE_URL)), src) if src else ""

    def _subjects(self, soup: BeautifulSoup) -> list[str]:
        links = soup.select(
            "a[href*='/sok/topic/'], a[href*='/sok/category/'], a[href*='/sok/classtree/']"
        )
        subjects = [self._text(link) for link in links]
        return sorted({subject for subject in subjects if subject})

    def _holdings(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Extract holdings conservatively."""
        holdings: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        candidates = soup.select(
            "li, tr, article, [class*='holding' i], [class*='exemplar' i], "
            "[class*='availability' i]"
        )

        for element in candidates:
            text = " ".join(element.get_text(separator=" ", strip=True).split())
            if not text or len(text) > 500:
                continue

            branch = self._branch_name(element)
            if not branch:
                continue

            available = self._is_available(element, text)
            shelf_mark = self._shelf_mark(element, text)
            item_id = self._item_id(element)
            key = (branch, item_id or text)

            if key in seen:
                continue
            seen.add(key)

            holdings.append(
                {
                    "branch": branch,
                    "available": available,
                    "shelf_mark": shelf_mark,
                    "item_id": item_id,
                    "raw_text": text,
                }
            )

        return holdings

    def _branch_name(self, element: Any) -> str:
        branch_element = element.select_one(
            "[class*='branch' i], [class*='bibliotek' i], [data-field*='branch' i]"
        )
        if branch_element:
            return self._text(branch_element)

        text = self._text(element)
        match = re.search(
            r"([A-ZÅÄÖ][\wåäöéèü\- ]+(?:bibliotek|Stadsbiblioteket))",
            text,
        )
        return match.group(1).strip() if match else ""

    def _is_available(self, element: Any, text: str) -> bool:
        classes = " ".join(element.get("class", [])).lower()
        lower_text = text.lower()

        if any(term in classes for term in ("available", "tillgänglig", "ledig")):
            return True
        if any(term in classes for term in ("unavailable", "utlånad", "reserverad")):
            return False

        if any(term in lower_text for term in ("tillgänglig", "ledig", "finns på hyllan")):
            return True
        if any(term in lower_text for term in ("utlånad", "reserverad", "ej tillgänglig")):
            return False

        return False

    def _shelf_mark(self, element: Any, text: str) -> str:
        shelf_element = element.select_one(
            "[class*='shelf' i], [class*='hylla' i], [data-field*='shelf' i]"
        )
        if shelf_element:
            return self._text(shelf_element)

        match = re.search(r"\b([A-ZÅÄÖ]{1,3}\d{1,4})\b", text)
        return match.group(1) if match else ""

    def _item_id(self, element: Any) -> str:
        item_element = element.select_one(
            "[data-item-id], [data-id], [class*='item' i]"
        )
        if item_element:
            return item_element.get("data-item-id") or item_element.get("data-id") or ""

        match = re.search(r"\b(\d{8,14})\b", self._text(element))
        return match.group(1) if match else ""


def build_search_url(
    query: str | None = None,
    author: str | None = None,
    isbn: str | None = None,
    branch: str | None = None,
    start: int = 0,
) -> str:
    """Build a human-readable search URL for debugging and documentation."""
    params: dict[str, str] = {}

    if query:
        params["text"] = query
    if author:
        params["author"] = author
    if isbn:
        params["text"] = isbn
    if branch:
        params["library"] = branch
    if start:
        params["start"] = str(start)

    return f"{SEARCH_URL}?{urlencode(params)}"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Search Stockholms stadsbibliotek")
    parser.add_argument("--author")
    parser.add_argument("--isbn")
    parser.add_argument("--query")
    parser.add_argument("--branch")
    parser.add_argument("--title-id")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--output", default="data/search-results.json")
    args = parser.parse_args()

    client = LibraryClient()

    if args.title_id:
        results = [client.get_title(args.title_id)]
    else:
        titles = client.search_titles(
            query=args.query,
            author=args.author,
            isbn=args.isbn,
            branch=args.branch,
            start=args.start,
        )
        results = []
        for title in titles:
            results.append(client.get_title(title["title_id"]))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(results)} records to {output}")


if __name__ == "__main__":
    main()
