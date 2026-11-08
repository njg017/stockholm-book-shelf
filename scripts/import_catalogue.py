"""Incrementally import and deduplicate discovered Stockholm Library titles."""
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
    imported, errors, duplicates = [], [], 0
    for title_id in selected:
        book = {'title_id': title_id, 'title': index['titles'][title_id].get('title') or '', 'shelves': []}
        try:
            enrich_title(client, book)
            if book.get('availability_status') == 'available':
                book.setdefault('shelves', []).append('available-now')
            enrich_record(book)
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
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'requested_batch': args.batch,
              'imported_count': len(imported), 'duplicate_records_merged': duplicates,
              'total_catalogue_works': len(records), 'remaining_discovered': len(pending) - len(selected),
              'errors': errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
