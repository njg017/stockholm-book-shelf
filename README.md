# Bokhyllan Stockholm

A Netflix-style discovery site for books available through **Stockholms stadsbibliotek**.

Instead of browsing a long catalogue list, visitors can browse visual book shelves by genre, language, branch and availability, then reserve titles through the library.

## Inspired by

This project is inspired by [stockholm-film-shelf](https://github.com/kmelkon/stockholm-film-shelf), which presents Stockholms stadsbibliotek’s DVD catalogue as a Netflix-style shelf. This project applies the same discovery pattern to books.

## Two-stage catalogue flow

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
Open Library enrichment → data/books.json + data/shelves.json
```

For example, a search for Gabrielle Zevin can return a title link such as:

```text
https://biblioteket.stockholm.se/titel/8487743?author=Gabrielle%20Zevin
```

The importer extracts the stable title ID (`8487743`), then requests the clean title URL:

```text
https://biblioteket.stockholm.se/titel/8487743
```

## What each stage extracts

| Stage | Extracted data |
|---|---|
| Search page | Title ID, title URL, visible search text and source URL |
| Title page | Title, author, ISBN, language, format, year, cover, description, subjects, holdings, branches and availability |

A title page can include several editions and formats. The importer treats `title_id` as the library work identifier and preserves holdings in the resulting record.

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
# Fetch up to 5 title pages per seed
python scripts/import_library.py --max-titles 5

# Import without Open Library enrichment
python scripts/import_library.py --no-enrich

# Use a longer delay between library requests
python scripts/import_library.py --delay 3
```

## Search a single title

```bash
python scripts/stockholm_library.py --title-id 8487743
```

Search by author:

```bash
python scripts/stockholm_library.py --author "Gabrielle Zevin"
```

Search by ISBN:

```bash
python scripts/stockholm_library.py --isbn 9780571364886
```

## What the importer produces

| File | Purpose |
|---|---|
| `data/books.json` | Deduplicated, enriched title records |
| `data/shelves.json` | Books grouped by shelf ID |
| `data/import-report.json` | Run timestamp, counts and errors |
| `data/raw/search/*.json` | Cached search responses |
| `data/raw/title/*.json` | Cached title-page responses |

## Automated refresh

`.github/workflows/update-data.yml` runs at 05:00 and 17:00 UTC each day. It can also be triggered manually from GitHub under **Actions → Update library data → Run workflow**.

## Offline tests

```bash
python scripts/test_search_client.py
```

## Responsible use

- Cache responses; do not make high-volume repeated requests.
- Use a descriptive User-Agent.
- Show a data-updated timestamp in the eventual UI.
- Treat availability as approximate and direct users to the official library catalogue for reservations.

## Status

**Two-stage importer implemented.** The next calibration step is to run one author search and one title-page fetch, inspect the cached HTML, and refine the selectors for the real result cards and holdings markup.
