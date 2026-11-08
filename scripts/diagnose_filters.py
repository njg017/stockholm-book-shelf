"""Inspect available catalogue filters and test language partitions."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = 'https://biblioteket.stockholm.se'
QUERY = '''query searchWithFilter($filterQuery: SearchWithFilterInput!) {
  searchWithFilter(filterQuery: $filterQuery) {
    start totalHits
    groupedMedia {
      mediaTypeEnum name numFound
      mediaList {
        id key title author availableInFormat mediaType mediaTypeDisplay
        mediaSubTypeDisplay image language languages targetGroup publisher
        publishedDate holdingIds
      }
    }
    availableFilterGroups { name filters { name count } }
  }
}'''

def graphql(session, filters):
    request = {'query': QUERY, 'variables': {'filterQuery': filters, '__operation': 'search'}, 'operationName': 'searchWithFilter'}
    response = session.post(BASE + '/graphql', json=request, timeout=30)
    try:
        payload = response.json()
    except Exception as exc:
        payload = {'decode_error': str(exc), 'text': response.text[:2000]}
    return response, payload

def summarize(payload):
    result = (payload.get('data') or {}).get('searchWithFilter') or {}
    books = []
    for group in result.get('groupedMedia') or []:
        if group.get('mediaTypeEnum') == 'BOOK':
            books.extend(group.get('mediaList') or [])
    ids = [str(book.get('key')) for book in books]
    return {'status': None, 'total_hits': result.get('totalHits'), 'returned': len(books),
            'first_id': ids[0] if ids else None, 'last_id': ids[-1] if ids else None,
            'facets': result.get('availableFilterGroups') or [], 'errors': payload.get('errors')}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=100)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    session = requests.Session()
    session.headers.update({'User-Agent': 'BokhyllanStockholm/0.2 (+https://github.com/njg017/stockholm-book-shelf)'})
    tests = []
    for label, filters in (
        ('unfiltered', {'query': '', 'rows': args.rows, 'mediaType': ['BOOK']}),
        ('english', {'query': '', 'rows': args.rows, 'mediaType': ['BOOK'], 'language': ['Engelska']}),
        ('swedish', {'query': '', 'rows': args.rows, 'mediaType': ['BOOK'], 'language': ['Svenska']}),
    ):
        response, payload = graphql(session, filters)
        summary = summarize(payload)
        summary.update({'label': label, 'status': response.status_code, 'request': filters})
        tests.append(summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        time.sleep(args.delay)
    output = Path('diagnostics') / 'filters.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'generated_at': datetime.now(timezone.utc).isoformat(), 'tests': tests}, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
