"""Refresh availability for a bounded rotating subset of catalogue records."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from library_graphql import GraphQLClient
from title_metadata import enrich_title

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
BOOKS = DATA / 'books.json'
AVAILABILITY = DATA / 'availability.json'
STATE = DATA / 'availability-cursor.json'

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, default=500)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    books = json.loads(BOOKS.read_text(encoding='utf-8')) if BOOKS.exists() else []
    availability = json.loads(AVAILABILITY.read_text(encoding='utf-8')) if AVAILABILITY.exists() else {}
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'offset': 0}
    ordered = sorted(books, key=lambda book: str(book['title_id']))
    selected = ordered[state['offset']:state['offset'] + args.batch]
    if len(selected) < args.batch:
        selected += ordered[:args.batch - len(selected)]
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    refreshed, errors = [], []
    for book in selected:
        try:
            enrich_title(client, book)
            refreshed.append(book)
        except Exception as exc:
            errors.append({'title_id': book.get('title_id'), 'error': str(exc)})
    for book in refreshed:
        availability[str(book['title_id'])] = {
            'holdings': book.get('holdings'), 'available_copies': book.get('available_copies'),
            'total_copies': book.get('total_copies'), 'available_branches': book.get('available_branches'),
            'availability_status': book.get('availability_status'),
            'availability_checked_at': book.get('availability_checked_at')
        }
    state['offset'] = (state['offset'] + args.batch) % max(1, len(ordered))
    write_json(AVAILABILITY, availability)
    write_json(STATE, state)
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'requested_batch': args.batch,
              'refreshed_count': len(refreshed), 'catalogue_size': len(ordered),
              'next_offset': state['offset'], 'errors': errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
