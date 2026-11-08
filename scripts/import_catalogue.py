"""Incrementally import, deduplicate, validate and publish Stockholm Library titles."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from enrich_openlibrary import enrich_record
from library_graphql import GraphQLClient
from title_metadata import enrich_title

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
INDEX = DATA / 'catalogue-index.json'
BOOKS = DATA / 'books.json'
AVAILABILITY = DATA / 'availability.json'
SITE_INDEX = DATA / 'catalogue' / 'index.json'
CHUNK_DIR = DATA / 'catalogue' / 'chunks'
CHUNK_SIZE = 200

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def normalize(value):
    return re.sub(r'\s+', ' ', (value or '')).strip().casefold()

def work_key(book):
    isbn = book.get('isbn') or next((value for value in book.get('isbns') or [] if isinstance(value, str)), None)
    if isbn:
        return 'isbn:' + normalize(isbn)
    return 'title:' + normalize(book.get('title')) + '|author:' + normalize(book.get('author'))

def validate(book):
    problems = []
    if not isinstance(book.get('title'), str) or not book.get('title').strip(): problems.append('missing_title')
    if not str(book.get('title_id') or '').isdigit(): problems.append('invalid_title_id')
    if not book.get('author'): problems.append('missing_author')
    if not book.get('isbn') and not list(book.get('isbns') or []): problems.append('missing_isbn')
    return problems

def split_catalogue(records):
    items = []
    for index, book in enumerate(records):
        items.append({'title_id': str(book['title_id']), 'title': book.get('title'), 'author': book.get('author'),
                      'language': book.get('language'), 'cover_url': book.get('cover_url'),
                      'genres': book.get('genres') or [], 'published_year': book.get('published_year'),
                      'is_recent_release': book.get('is_recent_release'),
                      'openlibrary_rating_average': book.get('openlibrary_rating_average'),
                      'openlibrary_rating_count': book.get('openlibrary_rating_count'),
                      'chunk': index // CHUNK_SIZE})
    chunks = [records[start:start + CHUNK_SIZE] for start in range(0, len(records), CHUNK_SIZE)]
    for number, chunk in enumerate(chunks):
        write_json(CHUNK_DIR / f'chunk-{number:04d}.json', chunk)
    write_json(SITE_INDEX, {'generated_at': datetime.now(timezone.utc).isoformat(), 'total': len(records),
                            'chunk_size': CHUNK_SIZE, 'chunk_count': len(chunks), 'items': items})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, default=100)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    index = json.loads(INDEX.read_text(encoding='utf-8')) if INDEX.exists() else {'titles': {}}
    books = json.loads(BOOKS.read_text(encoding='utf-8')) if BOOKS.exists() else []
    works = {}
    for book in books:
        key = work_key(book)
        current = works.get(key)
        if current is None:
            works[key] = book
        else:
            current.setdefault('related_title_ids', []).append(book['title_id'])
            current['quality_flags'] = sorted(set(current.get('quality_flags', []) + ['possible_duplicate_edition']))
    pending = [title_id for title_id, record in index.get('titles', {}).items()
               if not record.get('imported') and title_id not in {str(book['title_id']) for book in books}]
    pending.sort()
    selected = pending[:args.batch]
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    imported, errors, duplicates, invalid = [], [], 0, 0
    for title_id in selected:
        book = {'title_id': title_id, 'title': index['titles'][title_id].get('title') or '', 'shelves': []}
        try:
            enrich_title(client, book)
            if book.get('availability_status') == 'available':
                book.setdefault('shelves', []).append('available-now')
            enrich_record(book)
            problems = validate(book)
            if problems:
                invalid += 1
                book['quality_flags'] = sorted(set(book.get('quality_flags', []) + problems))
            key = work_key(book)
            current = works.get(key)
            if current:
                duplicates += 1
                current.setdefault('related_title_ids', []).append(title_id)
                current['quality_flags'] = sorted(set(current.get('quality_flags', []) + ['possible_duplicate_edition']))
            else:
                works[key] = book
            imported.append(book)
            index['titles'][title_id]['imported'] = True
            index['titles'][title_id]['imported_at'] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            errors.append({'title_id': title_id, 'error': str(exc)})
    records = list(works.values())
    availability = {}
    for book in records:
        availability[str(book['title_id'])] = {
            'holdings': book.get('holdings'), 'available_copies': book.get('available_copies'),
            'total_copies': book.get('total_copies'), 'available_branches': book.get('available_branches'),
            'availability_status': book.get('availability_status'),
            'availability_checked_at': book.get('availability_checked_at')
        }
    write_json(BOOKS, records)
    write_json(AVAILABILITY, availability)
    write_json(INDEX, index)
    split_catalogue(records)
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'requested_batch': args.batch,
              'imported_count': len(imported), 'duplicate_records_merged': duplicates,
              'invalid_records_flagged': invalid, 'total_catalogue_works': len(records),
              'remaining_discovered': len(pending) - len(selected), 'errors': errors}
    write_json(DATA / 'import-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
