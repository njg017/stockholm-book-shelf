# Bokhyllan Stockholm

A Netflix-style discovery site for books available through **Stockholms stadsbibliotek**.

Instead of browsing a long catalogue list, visitors can browse visual book shelves by genre, language, branch and availability, then reserve titles through the library.

**Live site:** https://njg017.github.io/stockholm-book-shelf/

## Inspired by

This project is inspired by [stockholm-film-shelf](https://github.com/kmelkon/stockholm-film-shelf), which presents Stockholms stadsbibliotek’s DVD catalogue as a Netflix-style shelf. This project applies the same discovery pattern to books.

## How it works

The importer uses the library’s two-stage structure:

```text
config/seeds.json
      ↓
Search page: /sok?author=Gabrielle+Zevin
      ↓
Extract /titel/<id> links
      ↓
Title page: /titel/8487743
      ↓
Extract metadata and holdings
      ↓
Open Library enrichment
      ↓
data/books.json + data/shelves.json
```

The catalogue is intentionally curated rather than exhaustive. `config/seeds.json` defines 21 author/shelf combinations, with up to 20 titles imported per seed.

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

## Run the importer

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the full configured catalogue:

```bash
python scripts/import_library.py --rows 20 --delay 2
```

Import one author only:

```bash
python scripts/import_library.py --author "Gabrielle Zevin" --rows 3 --delay 2
```

The importer reads all configured seeds when `--author` is omitted. It deduplicates records by library title ID, enriches each record, and writes the resulting catalogue files.

## Automated refresh

`.github/workflows/update-data.yml` runs daily at **03:17 UTC**. Scheduled runs automatically publish changed catalogue data to `main`.

You can also run it manually from GitHub under **Actions → Update library data → Run workflow**. For a manual run, enable **Publish** to commit updated `books.json`, `shelves.json` and `import-report.json` to `main`.

The importer is designed to tolerate partial failures: a failed seed, title enrichment, or Open Library request does not prevent publication of the books that imported successfully. It fails only when no books were imported. All errors are recorded in `data/import-report.json`.

## Inspect results

After a workflow run, download the `graphql-import` artifact. It contains:

| File | Purpose |
|---|---|
| `data/books.json` | Deduplicated, enriched title records |
| `data/shelves.json` | Books grouped by shelf ID |
| `data/import-report.json` | Run timestamp, book count, searches, errors and enrichment status |
| `data/raw/graphql/` | Cached library search responses |
| `data/raw/title-html/` | Cached title-page responses |

Useful report fields include `book_count`, `failed_seed_count`, `errors`, and `searches`.

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

**Live and under active development.** The site publishes a curated, Open Library–enriched selection from Stockholms stadsbibliotek. The catalogue is intentionally limited to configured seeds rather than the library’s full collection.
