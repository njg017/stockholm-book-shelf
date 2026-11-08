# Bokhyllan Stockholm

A Netflix-style discovery site for books available through **Stockholms stadsbibliotek**.

Instead of browsing a long catalogue list, visitors can browse visual book shelves by genre, language, branch and availability, then reserve titles through the library.

## Inspired by

This project is inspired by [stockholm-film-shelf](https://github.com/kmelkon/stockholm-film-shelf), which presents Stockholms stadsbibliotek’s DVD catalogue as a Netflix-style shelf. This project applies the same discovery pattern to books.

## MVP scope

The first version focuses on a curated set of English and Swedish fiction, crime, science fiction/fantasy and children’s books.

Core features:

- Horizontal, scrollable book shelves
- Filter by genre, language, format and branch
- Search by title, author, ISBN and subject
- Book detail view with cover, description and subjects
- Branch availability and reservation links
- Locally saved favourites using browser storage

## Architecture

```text
config/seeds.json
      ↓
Stockholms stadsbibliotek search
      ↓
Raw response cache → normalised records → Open Library enrichment
      ↓
data/books.json + data/shelves.json → static front end
```

- `scripts/stockholm_library.py` searches and normalises library records
- `scripts/import_library.py` runs the complete import pipeline
- `scripts/enrich_openlibrary.py` adds covers, descriptions and subjects
- `scripts/build_site_data.py` can rebuild shelf files from raw records
- `index.html` and `assets/` provide the initial static front end

## Run the importer

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run a full import:

```bash
python scripts/import_library.py
```

Useful options:

```bash
# Limit each seed search to 10 records
python scripts/import_library.py --max-results 10

# Import without calling Open Library
python scripts/import_library.py --no-enrich

# Use a longer delay between library requests
python scripts/import_library.py --delay 3
```

## What the importer produces

| File | Purpose |
|---|---|
| `data/books.json` | Deduplicated, enriched book records |
| `data/shelves.json` | Books grouped by shelf ID |
| `data/import-report.json` | Run timestamp, counts and errors |
| `data/raw/search/*.json` | Cached raw search responses for debugging |

The importer does not claim that availability is live. Every generated record includes an `updated_at` value, and the eventual front end should show when the data was last refreshed.

## Automated refresh

`.github/workflows/update-data.yml` runs at 05:00 and 17:00 UTC each day. It can also be triggered manually from GitHub under **Actions → Update library data → Run workflow**.

The workflow:

1. Installs Python dependencies
2. Runs the importer
3. Commits refreshed JSON and raw search caches
4. Pushes the update to `main`

## Search client

Run a single search directly:

```bash
python scripts/stockholm_library.py "9780571364886"
python scripts/stockholm_library.py "Gabrielle Zevin"
```

The client saves raw responses before parsing and uses a descriptive User-Agent. If the response structure cannot be understood, it raises an error rather than publishing unreliable data.

## Offline tests

```bash
python scripts/test_search_client.py
```

## Data model

See [`data/books.sample.json`](data/books.sample.json).

## Responsible use

- Cache responses; do not make high-volume repeated requests.
- Use a descriptive User-Agent.
- Show a data-updated timestamp in the eventual UI.
- Treat availability as approximate and direct users to the official library catalogue for reservations.

## Status

**Importer implemented.** Once the library site is available, run the importer, inspect `data/import-report.json` and the cached raw responses, then refine field extraction for holdings and branch availability.
