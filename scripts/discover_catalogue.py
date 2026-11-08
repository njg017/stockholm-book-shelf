"""Discover Stockholm Library title IDs through rotating public search queries."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from library_graphql import GraphQLClient

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
INDEX = DATA / 'catalogue-index.json'

QUERIES = [
    'svenska romaner', 'engelska romaner', 'deckare', 'thriller', 'fantasy',
    'science fiction', 'historisk roman', 'romantik', 'biografier', 'historia',
    'psykologi', 'filosofi', 'vetenskap', 'matlagning', 'barnböcker',
    'ungdomsböcker', 'grafiska romaner', 'poesi', 'resor', 'konst'
]

def normalize(value):
    return re.sub(r'\s+', ' ', (value or '')).strip().casefold()

def load_index():
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding='utf-8'))
    return {'version': 2, 'cursor': {'query_index': 0, 'page': 0}, 'titles': {}}

def save_index(index):
    index['discovered_at'] = datetime.now(timezone.utc).isoformat()
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    temp = INDEX.with_suffix('.tmp')
    temp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(INDEX)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--requests', type=int, default=20)
    parser.add_argument('--rows', type=int, default=50)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    index = load_index()
    cursor = index.setdefault('cursor', {'query_index': 0, 'page': 0})
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    added, errors, requests_used = 0, [], 0
    while requests_used < args.requests:
        query_index = cursor['query_index'] % len(QUERIES)
        page = cursor['page']
        query = QUERIES[query_index]
        try:
            result = client.search(query=query, rows=args.rows)
            requests_used += 1
            records = result['books']
            for book in records:
                title_id = str(book['title_id'])
                if title_id in index['titles']:
                    continue
                flags = []
                if not book.get('author'): flags.append('missing_author')
                if not book.get('isbn'): flags.append('missing_isbn')
                if not book.get('cover_url'): flags.append('missing_cover')
                index['titles'][title_id] = {
                    'title': book.get('title'), 'author': book.get('author'),
                    'language': book.get('language'), 'published_year': book.get('published_year'),
                    'discovered_query': query, 'discovered_page': page + 1,
                    'discovered_at': datetime.now(timezone.utc).isoformat(),
                    'imported': False, 'quality_flags': flags
                }
                added += 1
            cursor['page'] = page + 1
            if not result['partial']:
                cursor['query_index'] = query_index + 1
                cursor['page'] = 0
        except Exception as exc:
            errors.append({'query': query, 'page': page + 1, 'error': str(exc)})
            cursor['query_index'] = query_index + 1
            cursor['page'] = 0
    save_index(index)
    report = {'discovered_at': index['discovered_at'], 'known_titles': len(index['titles']),
              'newly_discovered': added, 'requests_used': requests_used,
              'next_cursor': cursor, 'errors': errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
