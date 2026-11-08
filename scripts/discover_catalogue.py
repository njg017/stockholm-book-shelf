"""Discover and queue Stockholm Library book titles using year ranges and branch slices."""
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
HARD_CAP = 900


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def year_filters(language, start, end):
    return {'language': [language], 'yearPublishedSpan': [str(start), str(end)]}


def branch_filters(language, branch, year=None):
    filters = {'language': [language]}
    if year is not None:
        filters['yearPublishedSpan'] = [str(year), str(year)]
    if branch:
        filters['branch'] = [branch]
    return filters


def facet_values(facets, needle):
    for group in facets or []:
        if needle.lower() in (group.get('name') or '').lower():
            return [{'name': item['name'], 'count': item.get('count') or 0}
                    for item in group.get('filters') or [] if item.get('name')]
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
    phases = cursor.setdefault('phases', {language: 'years' for language in languages})
    queue = cursor.setdefault('queue', [])
    if not queue:
        for language in languages:
            queue.append({'kind': 'years', 'language': language, 'from': args.start_year, 'to': args.end_year})
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    seen, errors = set(), []
    counters = {'queued': 0, 'reconciled': 0}
    fetches = 0

    while fetches < args.max_fetches and queue:
        task = queue.pop(0)
        kind = task['kind']
        language = task['language']
        try:
            if kind == 'years':
                start, end = int(task['from']), int(task['to'])
                probe = client.search(rows=1, filters=year_filters(language, start, end))
                fetches += 1
                total = probe.get('book_total') or 0
                if total == 0:
                    if start == end:
                        years[language] = start - 1
                    continue
                if total <= args.page_size:
                    result = client.search(rows=total, filters=year_filters(language, start, end))
                    fetches += 1
                    process_books(state, result.get('books') or [], imported_ids, seen, counters)
                    if start == end:
                        years[language] = start - 1
                    continue
                if start == end:
                    branches = facet_values(probe.get('facets'), 'bibliotek')
                    enqueued = 0
                    for branch in branches:
                        count = int(branch.get('count') or 0)
                        if count == 0:
                            continue
                        if count <= HARD_CAP:
                            queue.insert(0, {'kind': 'branch_year', 'language': language, 'year': start,
                                             'branch': branch['name'], 'total': count})
                            enqueued += 1
                        else:
                            errors.append({'partition': {'language': language, 'year': start, 'branch': branch['name']},
                                           'error': f'branch slice too large: {count} records'})
                    if enqueued == 0:
                        errors.append({'partition': {'language': language, 'year': start},
                                       'error': f'oversized year with {total} records and no usable branch slices'})
                    years[language] = start - 1
                    continue
                mid = (start + end) // 2
                queue.insert(0, {'kind': 'years', 'language': language, 'from': mid + 1, 'to': end})
                queue.insert(0, {'kind': 'years', 'language': language, 'from': start, 'to': mid})
            elif kind == 'branch_year':
                result = client.search(rows=min(int(task['total']), HARD_CAP),
                                       filters=branch_filters(language, task['branch'], task['year']))
                fetches += 1
                process_books(state, result.get('books') or [], imported_ids, seen, counters)
            elif kind == 'branch':
                result = client.search(rows=min(int(task['total']), HARD_CAP),
                                       filters=branch_filters(language, task['branch']))
                fetches += 1
                process_books(state, result.get('books') or [], imported_ids, seen, counters)
        except Exception as exc:
            errors.append({'partition': task, 'error': str(exc)})
        time.sleep(args.delay)

    if not args.dry_run:
        cursor['years'] = years
        cursor['phases'] = phases
        cursor['queue'] = queue
        cursor['last_run'] = {'at': datetime.now(timezone.utc).isoformat(), 'fetches': fetches,
                              'records_seen': len(seen), 'queued': counters['queued']}
        state.save()
    coverage = state.coverage()
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'dry_run': args.dry_run,
              'priority_languages': languages, 'page_size': args.page_size, 'fetches': fetches,
              'records_seen': len(seen), 'titles_queued_for_import': counters['queued'],
              'already_imported_titles_reconciled': counters['reconciled'],
              'cursor': {'years': years, 'phases': phases, 'queue_length': len(queue)},
              'coverage': coverage, 'errors': errors}
    write_json(REPORT, report)
    write_json(DATA / 'coverage-report.json', coverage)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
