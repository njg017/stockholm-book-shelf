"""Discover and queue Stockholm Library book titles using stable filter partitions."""
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

def build_partitions(years):
    partitions = []
    for language in ('Engelska', 'Svenska'):
        for year in years:
            for category in ('Skönlitteratur', 'Facklitteratur'):
                for audience in ('Vuxna', 'Barn och unga'):
                    partitions.append({'language': language, 'year': year, 'category': category, 'audience': audience})
    return partitions

def request_partition(client, partition, rows, start):
    filters = {'query': '', 'rows': rows, 'mediaType': ['BOOK'],
               'language': [partition['language']],
               'Utgivningsår': [partition['year']],
               'Kategori': [partition['category']],
               'Målgrupp': [partition['audience']]}
    if start:
        filters['start'] = start
    return client.search(filters=filters)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--page-size', type=int, default=500)
    parser.add_argument('--max-partitions', type=int, default=10)
    parser.add_argument('--delay', type=float, default=2)
    parser.add_argument('--languages', default='Engelska,Svenska', help='Comma-separated languages to prioritize for ingestion')
    parser.add_argument('--start-year', type=int, default=2026)
    parser.add_argument('--end-year', type=int, default=1900)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    priority = {value.strip() for value in args.languages.split(',') if value.strip()}
    state = IngestionState(STATE)
    imported_ids = set()
    if BOOKS.exists():
        try:
            books = json.loads(BOOKS.read_text(encoding='utf-8'))
            imported_ids = {str(book.get('title_id')) for book in books if book.get('title_id')}
        except (json.JSONDecodeError, OSError):
            pass
    years = list(range(args.start_year, args.end_year - 1, -1))
    partitions = build_partitions(years)
    cursor = state.data.setdefault('discovery', {})
    partition_index = int(cursor.get('partition_index', 0))
    record_offset = int(cursor.get('record_offset', 0))
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    seen, queued, already_imported, processed_partitions = set(), 0, 0, 0
    errors = []
    while partition_index < len(partitions) and processed_partitions < args.max_partitions:
        partition = partitions[partition_index]
        if partition['language'] not in priority:
            partition_index += 1
            record_offset = 0
            continue
        try:
            result = request_partition(client, partition, args.page_size, record_offset)
            books = result['books']
            for book in books:
                title_id = str(book['title_id'])
                if title_id in seen:
                    errors.append({'partition': partition, 'error': 'duplicate_title_id:' + title_id})
                    continue
                seen.add(title_id)
                record = state.ensure(title_id, book.get('title') or '')
                record.update({'title': book.get('title'), 'author': book.get('author'), 'language': book.get('language'),
                               'media_type': book.get('format'), 'discovered_at': datetime.now(timezone.utc).isoformat()})
                if title_id in imported_ids:
                    if record.get('status') != 'imported':
                        state.mark_imported(title_id)
                        already_imported += 1
                elif record.get('status') in {'discovered', 'failed'}:
                    record['status'] = 'pending'
                    record['priority'] = 'high'
                    queued += 1
            if not args.dry_run:
                state.save()
            processed_partitions += 1
            returned = len(books)
            if returned < args.page_size:
                partition_index += 1
                record_offset = 0
            else:
                record_offset += returned
        except Exception as exc:
            errors.append({'partition': partition, 'error': str(exc)})
            partition_index += 1
            record_offset = 0
        time.sleep(args.delay)
    if not args.dry_run:
        cursor['partition_index'] = partition_index
        cursor['record_offset'] = record_offset
        cursor['last_run'] = {'at': datetime.now(timezone.utc).isoformat(), 'partitions_processed': processed_partitions,
                              'records_seen': len(seen), 'queued': queued}
        state.save()
    coverage = state.coverage()
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'dry_run': args.dry_run,
              'priority_languages': sorted(priority), 'page_size': args.page_size,
              'partitions_processed': processed_partitions, 'records_seen': len(seen),
              'titles_queued_for_import': queued, 'already_imported_titles_reconciled': already_imported,
              'partition_index': partition_index, 'record_offset': record_offset,
              'coverage': coverage, 'errors': errors}
    write_json(REPORT, report)
    write_json(DATA / 'coverage-report.json', coverage)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
