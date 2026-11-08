"""Diagnose how the Stockholm Library catalogue API handles pagination."""
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
INTROSPECTION = '''query IntrospectSearchInput {
  __type(name: "SearchWithFilterInput") {
    name
    kind
    inputFields {
      name
      description
      type { kind name ofType { kind name ofType { kind name } } }
      defaultValue
    }
  }
}'''

def graphql(session, query, variables=None):
    request = {'query': query, 'variables': variables or {}, 'operationName': None}
    response = session.post(BASE + '/graphql', json=request, timeout=30)
    try:
        payload = response.json()
    except Exception as exc:
        payload = {'decode_error': str(exc), 'text': response.text[:2000]}
    return response, payload

def request_page(session, start, rows, offset_field):
    filters = {'query': '', 'rows': rows}
    if offset_field == 'page':
        filters['page'] = start // rows + 1
    else:
        filters[offset_field] = start
    response, payload = graphql(session, QUERY, {'filterQuery': filters, '__operation': 'search'})
    result = (payload.get('data') or {}).get('searchWithFilter') or {}
    books = []
    for group in result.get('groupedMedia') or []:
        if group.get('mediaTypeEnum') == 'BOOK':
            books.extend(group.get('mediaList') or [])
    ids = [str(book.get('key')) for book in books]
    return {'requested_start': start, 'offset_field': offset_field, 'status': response.status_code,
            'api_start': result.get('start'), 'total_hits': result.get('totalHits'),
            'returned': len(books), 'first_id': ids[0] if ids else None,
            'last_id': ids[-1] if ids else None, 'errors': payload.get('errors'),
            'request': {'query': QUERY, 'variables': {'filterQuery': filters, '__operation': 'search'}, 'operationName': 'searchWithFilter'}}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=50)
    parser.add_argument('--delay', type=float, default=2)
    args = parser.parse_args()
    session = requests.Session()
    session.headers.update({'User-Agent': 'BokhyllanStockholm/0.2 (+https://github.com/njg017/stockholm-book-shelf)'})
    response, introspection = graphql(session, INTROSPECTION)
    input_type = ((introspection.get('data') or {}).get('__type') or {})
    print('INTROSPECTION')
    print(json.dumps(introspection, ensure_ascii=False, indent=2))
    results = []
    fields = [field.get('name') for field in (input_type.get('inputFields') or [])]
    candidates = [field for field in fields if field in {'start', 'offset', 'skip', 'page', 'from', 'cursor', 'after', 'pageNumber'}]
    if not candidates:
        candidates = fields
    for field in candidates:
        for start in (0, 50, 100):
            result = request_page(session, start, args.rows, field)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))
            time.sleep(args.delay)
    output = Path('diagnostics') / 'pagination.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'generated_at': datetime.now(timezone.utc).isoformat(),
                                  'introspection': introspection, 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
