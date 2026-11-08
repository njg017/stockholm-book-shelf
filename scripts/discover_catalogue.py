"""Discover and queue Stockholm Library book titles using year and genre partitions."""
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
BOOKS = DATA / 'books.json'
REPORT = DATA / 'discovery-report.json'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def year_filters(language, year):
    return {'language': [language], 'yearPublishedSpan': [str(year), str(year)]}


def partition_filters(part):
    filters = year_filters(part['language'], part['year'])
    if part.get('genre'):
        filters['genre'] = [part['genre']]
    if part.get('subject'):
        filters['subject'] = [part['subject']]
    return filters


def facet_values(facets, needles):
    for group in facets or []:
        name = (group.get('name') or '').lower()
        if any(needle in name for needle in needles):
            return [item['name'] for item in group.get('filters') or [] if item.get('name')]
    return []


def process_books(state, books, imported_ids, seen, counters):
    for book in books:
        title_id = str(book['title_id'])
        if title_id in seen:
            continue
        seen.add(title_id)
        record = state.ensure(title_id, book.get('title') or '')
        record.update({'title': book.get('title'), 'author': book.get('author'), 'language': book.get('language'),
                       'media_type': book.get('format'), 'discovered_at': datetime.now(timezone.utc).isoformat()})
        if title_id in imported_ids:
            if record.get('status') != 'imported':
                state.mark_imported(title_id)
                counters['reconciled'] += 1
        elif record.get('status') in {'discovered', 'failed'}:
            record['status'] = 'pending'
            record['priority'] = 'high'
            counters['queued'] += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--page-size', type=int, default=500)
    parser.add_argument('--max-fetches', type=int, default=10)
    parser.add_argument('--delay', type=float, default=2)
    parser.add_argument('--languages', default='Engelska,Svenska')
    parser.add_argument('--start-year', type=int, default=2026)
    parser.add_argument('--end-year', type=int, default=1900)
    parser.add_argument('--reset-cursor', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    languages = [value.strip() for value in args.languages.split(',') if value.strip()]
    state = IngestionState(STATE)
    imported_ids = set()
    if BOOKS.exists():
        try:
            books = json.loads(BOOKS.read_text(encoding='utf-8'))
            imported_ids = {str(book.get('title_id')) for book in books if book.get('title_id')}
        except (json.JSONDecodeError, OSError):
            pass
    cursor = state.data.setdefault('discovery', {})
    if args.reset_cursor:
        cursor.clear()
    years = cursor.setdefault('years', {language: args.start_year for language in languages})
    queue = cursor.setdefault('queue', [])
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    seen, errors = set(), []
    counters = {'queued': 0, 'reconciled': 0}
    fetches = 0

    def next_language():
        active = [(int(years[language]), language) for language in languages if int(years.get(language, args.end_year)) >= args.end_year]
        return max(active)[1] if active else None

    while fetches < args.max_fetches:
        if queue:
            part = queue.pop(0)
            filters = partition_filters(part)
            if part.get('needs_probe'):
                probe = client.search(rows=1, filters=filters)
                fetches += 1
                total = probe.get('book_total') or 0
                if total == 0:
                    continue
                if total <= args.page_size:
                    part['total'] = total
                    part['needs_probe'] = False
                    queue.insert(0, part)
                    continue
                subjects = facet_values(probe.get('facets'), ['ämne', 'subject'])
                if subjects:
                    for subject in subjects:
                        queue.insert(0, {'language': part['language'], 'year': part['year'], 'genre': part.get('genre'),
                                         'subject': subject, 'total': None, 'needs_probe': True})
                    continue
                errors.append({'partition': part, 'error': f'oversized partition with {total} records and no subject facets'})
                continue
            result = client.search(rows=min(args.page_size, int(part.get('total') or args.page_size)), filters=filters)
            fetches += 1
            process_books(state, result.get('books') or [], imported_ids, seen, counters)
            continue
        language = next_language()
        if language is None:
            break
        year = int(years[language])
        probe = client.search(rows=1, filters=year_filters(language, year))
        fetches += 1
        total = probe.get('book_total') or 0
        if total == 0:
            years[language] = year - 1
            continue
        if total <= args.page_size:
            result = client.search(rows=total, filters=year_filters(language, year))
            fetches += 1
            process_books(state, result.get('books') or [], imported_ids, seen, counters)
            years[language] = year - 1
            continue
        genres = facet_values(probe.get('facets'), ['genre'])
        if genres:
            for genre in genres:
                queue.append({'language': language, 'year': year, 'genre': genre, 'subject': None,
                              'total': None, 'needs_probe': True})
        else:
            errors.append({'partition': {'language': language, 'year': year},
                           'error': f'oversized year with {total} records and no genre facets'})
        years[language] = year - 1

    if not args.dry_run:
        cursor['years'] = years
        cursor['queue'] = queue
        cursor['last_run'] = {'at': datetime.now(timezone.utc).isoformat(), 'fetches': fetches,
                              'records_seen': len(seen), 'queued': counters['queued']}
        state.save()
    coverage = state.coverage()
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'dry_run': args.dry_run,
              'priority_languages': languages, 'page_size': args.page_size, 'fetches': fetches,
              'records_seen': len(seen), 'titles_queued_for_import': counters['queued'],
              'already_imported_titles_reconciled': counters['reconciled'],
              'cursor': {'years': years, 'queue_length': len(queue)},
              'coverage': coverage, 'errors': errors}
    write_json(REPORT, report)
    write_json(DATA / 'coverage-report.json', coverage)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
