"""Resumable importer for Stockholm Library catalogue records."""
import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from enrich_openlibrary import enrich_record
from ingestion_state import IngestionState
from library_graphql import GraphQLClient
from title_metadata import enrich_title

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
INDEX = DATA / 'catalogue-index.json'
BOOKS = DATA / 'books.json'
AVAILABILITY = DATA / 'availability.json'
STATE = DATA / 'ingestion-state.json'
SITE_INDEX = DATA / 'catalogue' / 'index.json'
CHUNK_DIR = DATA / 'catalogue' / 'chunks'
CACHE_DIR = DATA / 'raw' / 'openlibrary'
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
    for position, book in enumerate(records):
        items.append({'title_id': str(book['title_id']), 'title': book.get('title'), 'author': book.get('author'),
                      'language': book.get('language'), 'cover_url': book.get('cover_url'),
                      'genres': book.get('genres') or [], 'published_year': book.get('published_year'),
                      'is_recent_release': book.get('is_recent_release'),
                      'openlibrary_rating_average': book.get('openlibrary_rating_average'),
                      'openlibrary_rating_count': book.get('openlibrary_rating_count'),
                      'chunk': position // CHUNK_SIZE})
    chunks = [records[start:start + CHUNK_SIZE] for start in range(0, len(records), CHUNK_SIZE)]
    for number, chunk in enumerate(chunks):
        write_json(CHUNK_DIR / f'chunk-{number:04d}.json', chunk)
    write_json(SITE_INDEX, {'generated_at': datetime.now(timezone.utc).isoformat(), 'total': len(records),
                            'chunk_size': CHUNK_SIZE, 'chunk_count': len(chunks), 'items': items})

def cached_open_library_enrichment(book):
    isbn = book.get('isbn')
    if not isbn:
        return enrich_record(book)
    key = hashlib.sha256(f'openlibrary:{isbn}'.encode()).hexdigest()[:24]
    cache_path = CACHE_DIR / f'{key}.json'
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding='utf-8'))
            book.update({key: value for key, value in cached.items() if key not in {'title_id', 'holdings', 'available_copies', 'total_copies', 'available_branches', 'availability_status', 'availability_checked_at'}})
            return book
        except (json.JSONDecodeError, OSError):
            pass
    enriched = enrich_record(book)
    payload = {key: value for key, value in enriched.items() if key not in {'title_id', 'holdings', 'available_copies', 'total_copies', 'available_branches', 'availability_status', 'availability_checked_at'}}
    write_json(cache_path, payload)
    return enriched

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, default=100)
    parser.add_argument('--delay', type=float, default=2)
    parser.add_argument('--openlibrary-workers', type=int, default=4)
    parser.add_argument('--limit', type=int, help='Maximum titles to process in this run')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-resume', action='store_true', help='Process pending titles even if previously failed')
    args = parser.parse_args()
    index = json.loads(INDEX.read_text(encoding='utf-8')) if INDEX.exists() else {'titles': {}}
    books = json.loads(BOOKS.read_text(encoding='utf-8')) if BOOKS.exists() else []
    state = IngestionState(STATE)
    imported_ids = {str(book['title_id']) for book in books}
    for title_id in list(state.data['titles']):
        if title_id in imported_ids and state.data['titles'][title_id].get('status') != 'imported':
            state.mark_imported(title_id)
    for title_id, record in index.get('titles', {}).items():
        state.ensure(title_id, record.get('title') or '')
        if title_id in imported_ids and state.data['titles'][title_id].get('status') != 'imported':
            state.mark_imported(title_id)
    state.save()
    limit = args.batch if args.limit is None else min(args.batch, args.limit)
    selected = [title_id for title_id in state.pending(limit) if title_id not in imported_ids]
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    imported, errors, duplicates, invalid = [], [], 0, 0
    works = {}
    for book in books:
        key = work_key(book)
        current = works.get(key)
        if current is None:
            works[key] = book
        else:
            current.setdefault('related_title_ids', []).append(book['title_id'])
            current['quality_flags'] = sorted(set(current.get('quality_flags', []) + ['possible_duplicate_edition']))
    pending = []
    records_by_id = {}
    for title_id in selected:
        if args.dry_run:
            imported.append({'title_id': title_id, 'dry_run': True})
            continue
        record = state.data['titles'][title_id]
        records_by_id[title_id] = record
        book = {'title_id': title_id, 'title': record.get('title') or '', 'shelves': []}
        try:
            enrich_title(client, book)
            pending.append(book)
        except Exception as exc:
            errors.append({'title_id': title_id, 'error': str(exc)})
            state.mark_failed(title_id, exc)
        time.sleep(args.delay)
    if pending and not args.dry_run:
        with_isbn = [book for book in pending if book.get('isbn')]
        without_isbn = [book for book in pending if not book.get('isbn')]
        for book in without_isbn:
            book.setdefault('quality_flags', []).append('openlibrary_skipped_no_isbn')
        if with_isbn:
            with ThreadPoolExecutor(max_workers=max(1, args.openlibrary_workers)) as pool:
                futures = [pool.submit(cached_open_library_enrichment, book) for book in with_isbn]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        errors.append({'stage': 'openlibrary', 'error': str(exc)})
    for book in pending:
        title_id = str(book['title_id'])
        record = records_by_id[title_id]
        try:
            if book.get('availability_status') == 'available':
                book.setdefault('shelves', []).append('available-now')
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
                state.mark_skipped(title_id, 'duplicate_edition')
            else:
                works[key] = book
                imported.append(book)
                state.mark_imported(title_id)
            index_entry = index.setdefault('titles', {}).setdefault(title_id, {'title': record.get('title') or ''})
            index_entry['imported'] = True
            index_entry['imported_at'] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            errors.append({'title_id': title_id, 'error': str(exc)})
            state.mark_failed(title_id, exc)
    if not args.dry_run:
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
    state.save()
    coverage = state.coverage()
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'dry_run': args.dry_run,
              'requested_batch': args.batch, 'processed': len(selected), 'imported_count': len([item for item in imported if not item.get('dry_run')]),
              'duplicate_records_merged': duplicates, 'invalid_records_flagged': invalid,
              'remaining_failed': coverage['failed'], 'remaining_pending': coverage['pending'],
              'coverage': coverage, 'errors': errors}
    write_json(DATA / 'import-report.json', report)
    write_json(DATA / 'coverage-report.json', coverage)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
