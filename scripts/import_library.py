"""Import search records and enrich from title-page embedded state."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from library_graphql import GraphQLClient
from title_metadata import enrich_title

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--author')
    parser.add_argument('--rows', type=int, default=3)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    config = json.loads((ROOT / 'config/seeds.json').read_text(encoding='utf-8'))
    seeds = [{'author': args.author}] if args.author else config['seeds']
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    books, errors, searches = {}, [], []
    for seed in seeds:
        try:
            result = client.search(author=seed.get('author'), query=seed.get('query', ''), rows=args.rows)
            searches.append({'author': seed.get('author'), **{k: result[k] for k in ('total_hits', 'groups', 'partial')}})
            for book in result['books']:
                books[book['title_id']] = book
        except Exception as exc:
            errors.append({'stage': 'search', 'seed': seed, 'error': str(exc)})
    for key, book in books.items():
        try:
            enrich_title(client, book)
            if book['availability_status'] == 'available':
                book['shelves'].append('available-now')
        except Exception as exc:
            errors.append({'stage': 'title', 'title_id': key, 'error': str(exc)})
    publish = bool(books) and not errors
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'published': publish,
              'book_count': len(books), 'errors': errors, 'searches': searches,
              'pagination_verified': False, 'availability_source': 'title-page branch counts'}
    write_json(DATA / 'import-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not publish:
        raise SystemExit('Previous books and shelves retained; inspect import-report.json')
    records, shelves = list(books.values()), {}
    for book in records:
        for shelf in book['shelves']:
            shelves.setdefault(shelf, []).append(book)
    write_json(DATA / 'books.json', records)
    write_json(DATA / 'shelves.json', shelves)

if __name__ == '__main__':
    main()
