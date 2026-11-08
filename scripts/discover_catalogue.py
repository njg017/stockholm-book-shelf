"""Discover Stockholm Library title IDs through broad public search queries."""
import argparse
import json
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

def load_index():
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding='utf-8'))
    return {'version': 1, 'discovered_at': None, 'titles': {}}

def save_index(index):
    index['discovered_at'] = datetime.now(timezone.utc).isoformat()
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    temp = INDEX.with_suffix('.tmp')
    temp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(INDEX)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pages-per-query', type=int, default=2)
    parser.add_argument('--rows', type=int, default=50)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    index = load_index()
    client = GraphQLClient(args.delay, DATA / 'raw/graphql')
    added, errors = 0, []
    for query in QUERIES:
        for page in range(args.pages_per_query):
            try:
                result = client.search(query=query, rows=args.rows)
                for book in result['books']:
                    title_id = str(book['title_id'])
                    if title_id not in index['titles']:
                        index['titles'][title_id] = {
                            'title': book.get('title'), 'author': book.get('author'),
                            'language': book.get('language'), 'published_year': book.get('published_year'),
                            'discovered_query': query, 'discovered_at': datetime.now(timezone.utc).isoformat(),
                            'imported': False
                        }
                        added += 1
            except Exception as exc:
                errors.append({'query': query, 'page': page + 1, 'error': str(exc)})
    save_index(index)
    report = {'discovered_at': index['discovered_at'], 'known_titles': len(index['titles']),
              'newly_discovered': added, 'errors': errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
