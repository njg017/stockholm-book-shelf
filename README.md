# Bokhyllan Stockholm

A Netflix-style discovery site for books available through **Stockholms stadsbibliotek**.

Instead of browsing a long catalogue list, visitors can browse visual book shelves by genre, language, branch and availability, then reserve titles through the library.

## Inspired by

This project is inspired by [stockholm-film-shelf](https://github.com/kmelkon/stockholm-film-shelf), which presents Stockholms stadsbibliotek’s DVD catalogue as a Netflix-style shelf. This project applies the same discovery pattern to books.

## MVP scope

The first version will focus on **English-language adult fiction available to borrow** through Stockholms stadsbibliotek.

Core features:

- Horizontal, scrollable book shelves
- Filter by genre, language, format and branch
- Search by title, author, ISBN and subject
- Book detail view with cover, description and subjects
- Branch availability and reservation links
- Locally saved favourites using browser storage

## Architecture

```text
Library catalogue → search client → raw cache → normalised JSON → static front end
                                        ↓
                             Open Library enrichment
```

- `scripts/stockholm_library.py` searches and normalises library records
- `scripts/enrich_openlibrary.py` adds covers, descriptions and subjects
- `scripts/build_site_data.py` produces the JSON consumed by the site
- `index.html` and `assets/` provide the initial static front end
- GitHub Pages can serve the static site

## Search client

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run a search:

```bash
python scripts/stockholm_library.py "9780571364886"
python scripts/stockholm_library.py "Gabrielle Zevin"
python scripts/stockholm_library.py "Gabrielle Zevin" --page 2
```

The client requests:

```text
https://biblioteket.stockholm.se/sok?text=<query>
```

It saves every raw response beneath `data/raw/search/` before attempting to parse it. This makes it possible to inspect the real response format and refine the parser without repeatedly requesting the live site.

The parser first looks for embedded JSON, JSON-LD and common Next.js/Nuxt state blocks. If none is found, it falls back to result links. The parser is intentionally conservative: it raises an error rather than inventing fields when the response cannot be understood.

Run offline tests:

```bash
python scripts/test_search_client.py
```

## Data model

See [`data/books.sample.json`](data/books.sample.json).

## Roadmap

1. Run the search client once the library site is available
2. Inspect the saved raw response in `data/raw/search/`
3. Replace the generic parser with selectors matched to the real response
4. Add holdings, branch and availability extraction
5. Enrich records with Open Library metadata
6. Build shelf UI, filters and book detail pages
7. Automate data refresh with GitHub Actions

## Responsible use

- Cache responses; do not make high-volume repeated requests.
- Use a descriptive User-Agent.
- Show a data-updated timestamp in the eventual UI.
- Treat availability as approximate and direct users to the official library catalogue for reservations.

## Status

**Search client scaffold complete.** The next step is to run it against the live catalogue once maintenance ends, inspect the cached response, and tailor the parser to its actual structure.
