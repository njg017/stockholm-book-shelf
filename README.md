# Bokhyllan Stockholm

A Netflix-style discovery site for books available through **Stockholms stadsbibliotek**.

Instead of browsing a long catalogue list, visitors can browse visual book shelves by genre, language, branch and availability, then reserve titles through the library.

**Live site:** https://njg017.github.io/stockholm-book-shelf/

## Inspired by

This project is inspired by [stockholm-film-shelf](https://github.com/kmelkon/stockholm-film-shelf), which presents Stockholms stadsbibliotek’s DVD catalogue as a Netflix-style shelf. This project applies the same discovery pattern to books.

## How it works

The pipeline expands the catalogue in two stages:

```text
GraphQL catalogue search
      ↓
Year-range bisection and branch slices
      ↓
New title IDs queued in ingestion-state.json
      ↓
Title page: /titel/<id>
      ↓
Extract metadata and holdings
      ↓
Open Library enrichment
      ↓
data/books.json + data/shelves.json
```

Discovery prioritizes English (`Engelska`) and Swedish (`Svenska`) books. It uses the library’s GraphQL search API with `yearPublishedSpan` filters, bisecting year ranges until each slice fits in a single request. Oversized single years are subdivided by library branch, and a final branch-only pass catches titles without a publication year.

The API does not support offset pagination, so discovery never relies on `start` offsets. Each request is capped at 900 records, and slices are kept at 500 records or fewer whenever possible. Duplicate title IDs are merged, so overlapping branch slices do not create duplicate books.

## What the site shows

The site supports:

- Search across title, author, ISBN, description, subjects and genres
- Branch, language and genre filters
- Availability filtering for a selected branch
- Open Library ratings and rating counts
- A recent-release filter and “New release” badges
- Sorting by relevance, highest rating, or most recently published
- A detail modal with metadata, branch availability, reservation link and data timestamps

Availability is a timestamped snapshot, not live stock. Visitors should use the official library catalogue before travelling or reserving.

## Open Library enrichment

After importing a title from Stockholms stadsbibliotek, the pipeline queries Open Library by ISBN and adds:

| Field | Meaning |
|---|---|
| `openlibrary_work_id` | Open Library work identifier |
| `openlibrary_rating_average` | Community average rating, when available |
| `openlibrary_rating_count` | Number of Open Library ratings |
| `first_published_year` | First publication year for the underlying work |
| `is_recent_release` | True when the edition was published within the last three years |
| `cover_url`, `description`, `subjects` | Added only when not already supplied by the library source |

Open Library data is community-contributed and may be incomplete. The site therefore treats missing ratings and metadata as normal rather than errors.

## Run the pipeline locally

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Discover and queue new titles:

```bash
python scripts/discover_catalogue.py --page-size 500 --max-fetches 10 --delay 2
```

Import the next batch of queued titles:

```bash
python scripts/import_catalogue.py --batch 25 --delay 2
```

Reset discovery to start from the newest publications again:

```bash
python scripts/discover_catalogue.py --page-size 500 --max-fetches 10 --delay 2 --reset-cursor
```

Discovery is resumable: the current year ranges, branch slices and pending queue are stored in `data/ingestion-state.json`. The importer processes pending titles, enriches them, deduplicates editions, and writes the resulting catalogue files.

## Automated refresh

`.github/workflows/update-data.yml` runs daily at **03:17 UTC**. Scheduled runs automatically publish changed catalogue data to `main`.

You can also run it manually from GitHub under **Actions → Expand catalogue metadata → Run workflow**.

| Input | Purpose |
|---|---|
| `Publish` | Commit updated catalogue JSON to `main` |
| `Batch` | Number of new titles to import per run |
| `Fetches` | Number of catalogue API requests for discovery per run |
| `Reset cursor` | Restart discovery from the newest publications |

For a manual run, enable **Publish** to commit updated `books.json`, `shelves.json`, `import-report.json`, `discovery-report.json` and `coverage-report.json` to `main`.

The pipeline is designed to tolerate partial failures: a failed title enrichment or Open Library request does not prevent publication of the books that imported successfully. Errors are recorded in `data/import-report.json` and `data/discovery-report.json`.

## Inspect results

After a workflow run, download the `catalogue-metadata` artifact. It contains:

| File | Purpose |
|---|---|
| `data/books.json` | Deduplicated, enriched title records |
| `data/shelves.json` | Books grouped by shelf ID |
| `data/import-report.json` | Imported titles, duplicates, invalid records and errors |
| `data/discovery-report.json` | Discovery fetches, records seen, queued titles and cursor state |
| `data/coverage-report.json` | Discovered, imported, pending, failed and skipped title counts |
| `data/raw/graphql/` | Cached library search responses |
| `data/raw/title-html/` | Cached title-page responses |

Useful report fields include `records_seen`, `titles_queued_for_import`, `fetches`, `cursor`, `processed`, `imported_count`, and `errors`.

## Browser smoke test

`.github/workflows/test-website.yml` is a manual Chromium test. It serves the repository locally, loads the real `books.json`, and checks that cards, search, filters, the detail modal, availability filtering and mobile layout work.

Run it from **Actions → Test website in Chromium → Run workflow**. The workflow uploads desktop and mobile screenshots, rendered HTML, and a `results.json` file that lists JavaScript errors.

## Responsible use

- Cache responses; do not make high-volume repeated requests.
- Use a descriptive User-Agent.
- Show a data-updated timestamp in the UI.
- Treat availability as approximate and direct users to the official library catalogue for reservations.
- Respect the public APIs used for enrichment and avoid unnecessary duplicate requests.

## Status

**Live and under active development.** The site automatically expands its English and Swedish catalogue coverage through resumable, partition-based discovery. Titles are enriched with library metadata and Open Library data, then published as searchable shelves.
