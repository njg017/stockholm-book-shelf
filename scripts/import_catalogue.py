"""Incrementally import discovered Stockholm Library titles."""
import argparse
import json
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, default=100)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    index = json.loads(INDEX.read_text(encoding='utf-8')) if INDEX.exists() else {'titles': {}}
    books = json.loads(BOOKS.read_text(encoding='utf-8')) if BOOKS.exists() else []
    existing = {str(book['title_id']): book for book in books}
    pending = [title_id for title_id, record in index.get('titles', {}).items() if not record.get('imported') and title_id not in existing]
    pending.sort()
    selected = pending[:args.batch]
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    imported, errors = [], []
    for title_id in selected:
        book = {'title_id': title_id, 'title': index['titles'][title_id].get('title') or '', 'shelves': []}
        try:
            enrich_title(client, book)
            if book.get('availability_status') == 'available':
                book.setdefault('shelves', []).append('available-now')
            enrich_record(book)
            imported.append(book)
            index['titles'][title_id]['imported'] = True
            index['titles'][title_id]['imported_at'] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            errors.append({'title_id': title_id, 'error': str(exc)})
    for book in imported:
        existing[str(book['title_id'])] = book
    records = list(existing.values())
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
              'imported_count': len(imported), 'total_catalogue_records': len(records),
              'remaining_discovered': len(pending) - len(selected), 'errors': errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
