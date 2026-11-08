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
Library catalogue → importer → normalised JSON → static front end
                        ↓
              Open Library enrichment
```

- `scripts/fetch_library.py` fetches and normalises library records
- `scripts/enrich_openlibrary.py` adds covers, descriptions and subjects
- `scripts/build_site_data.py` produces the JSON consumed by the site
- `index.html` and `assets/` provide the initial static front end
- GitHub Pages can serve the static site

## Data model

See [`data/books.sample.json`](data/books.sample.json).

## Roadmap

1. Validate the library catalogue data fields
2. Build a small importer for a 200-book test set
3. Enrich records with Open Library metadata
4. Build shelf UI, filters and book detail pages
5. Automate data refresh with GitHub Actions
6. Add read-alikes, branch pages and personalised shelves

## Status

**Initial scaffold.** The importer and front end are intentionally lightweight starting points; the next milestone is to inspect the library catalogue response format and implement a real fetcher.
