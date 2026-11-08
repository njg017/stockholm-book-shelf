"""Discover and queue Stockholm Library book titles, prioritising English and Swedish."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from ingestion_state import IngestionState
from library_graphql import GraphQLClient

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
STATE = DATA / 'ingestion-state.json'
REPORT = DATA / 'discovery-report.json'
FALLBACK_SIZES = (100, 50, 20, 3)

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def search_page(client, requested_size, start):
    errors = []
    sizes = [size for size in FALLBACK_SIZES if size <= requested_size] or [3]
    for size in sizes:
        try:
            result = client.search(query='', rows=size, start=start)
            return result, size, errors
        except Exception as exc:
            errors.append({'requested_page_size': requested_size, 'attempted_page_size': size, 'start': start, 'error': str(exc)})
    return None, requested_size, errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--page-size', type=int, default=100)
    parser.add_argument('--max-pages', type=int, default=10)
    parser.add_argument('--delay', type=float, default=2)
    parser.add_argument('--languages', default='Engelska,Svenska', help='Comma-separated languages to prioritize for ingestion')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    priority = {value.strip() for value in args.languages.split(',') if value.strip()}
    state = IngestionState(STATE)
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    seen, queued, pages = set(), 0, 0
    start = 0
    effective_size = args.page_size
    total_hits = book_total = None
    errors = []
    while pages < args.max_pages:
        result, used_size, page_errors = search_page(client, effective_size, start)
        errors.extend(page_errors)
        if result is None:
            break
        effective_size = used_size
        pages += 1
        books = result['books']
        total_hits = result['total_hits']
        book_total = result['book_total'] if book_total is None else book_total
        for book in books:
            title_id = str(book['title_id'])
            if title_id in seen:
                errors.append({'page': pages, 'start': start, 'error': 'duplicate_title_id:' + title_id})
                continue
            seen.add(title_id)
            record = state.ensure(title_id, book.get('title') or '')
            record.update({'title': book.get('title'), 'author': book.get('author'), 'language': book.get('language'),
                           'media_type': book.get('format'), 'discovered_at': datetime.now(timezone.utc).isoformat()})
            if record.get('status') in {'discovered', 'failed'} and book.get('language') in priority:
                record['status'] = 'pending'
                record['priority'] = 'high'
                queued += 1
        if not args.dry_run:
            state.save()
        returned = len(books)
        if returned < effective_size or (book_total is not None and start + returned >= book_total):
            break
        start += returned
        time.sleep(args.delay)
    coverage = state.coverage()
    pagination_verified = bool(book_total is not None and pages and not errors and len(seen) <= book_total and (len(seen) == book_total or pages < args.max_pages))
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'dry_run': args.dry_run,
              'priority_languages': sorted(priority), 'requested_page_size': args.page_size,
              'effective_page_size': effective_size, 'pages_fetched': pages, 'records_seen': len(seen),
              'titles_queued_for_import': queued, 'total_hits': total_hits, 'book_total': book_total,
              'pagination_verified': pagination_verified, 'coverage': coverage, 'errors': errors}
    write_json(REPORT, report)
    write_json(DATA / 'coverage-report.json', coverage)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
