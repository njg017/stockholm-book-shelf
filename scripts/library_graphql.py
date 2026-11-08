"""Catalogue search using the browser-captured GraphQL operation."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
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

class CatalogueError(RuntimeError):
    pass

def parse_response(payload):
    if payload.get('errors'):
        raise CatalogueError(json.dumps(payload['errors'], ensure_ascii=False))
    result = (payload.get('data') or {}).get('searchWithFilter')
    if not isinstance(result, dict) or not isinstance(result.get('groupedMedia'), list):
        raise CatalogueError('Missing searchWithFilter result groups')
    books, groups = [], []
    book_total = None
    for group in result['groupedMedia']:
        records = group.get('mediaList') or []
        groups.append({'format': group.get('mediaTypeEnum'), 'total': group.get('numFound'), 'returned': len(records)})
        if group.get('mediaTypeEnum') != 'BOOK':
            continue
        book_total = group.get('numFound')
        for media in records:
            key = str(media.get('key') or '')
            if not key.isdigit() or not media.get('title'):
                raise CatalogueError('Book missing numeric library key or title')
            language = media.get('language')
            shelves = ['books']
            if language == 'Engelska':
                shelves.append('english-books')
            elif language == 'Svenska':
                shelves.append('swedish-books')
            date = media.get('publishedDate')
            books.append({
                'id': media.get('id'), 'title_id': key, 'title': media['title'],
                'author': media.get('author'), 'format': media.get('mediaType'),
                'format_label': media.get('mediaSubTypeDisplay'),
                'language': language, 'languages': media.get('languages'),
                'target_group': media.get('targetGroup'), 'publisher': media.get('publisher'),
                'published_date': date,
                'published_year': int(date) if isinstance(date, str) and len(date) == 4 and date.isdigit() else None,
                'cover_url': urljoin(BASE, media['image']) if media.get('image') else None,
                'reservation_url': f'{BASE}/titel/{key}',
                'isbn': None, 'description': None, 'subjects': [],
                'holding_ids': media.get('holdingIds'), 'available_in_format': media.get('availableInFormat'),
                'holdings': None, 'available_copies': None, 'total_copies': None,
                'available_branches': None, 'availability_status': 'unknown',
                'shelves': shelves,
            })
    return {'books': books, 'total_hits': result.get('totalHits'), 'book_total': book_total, 'start': result.get('start'),
            'groups': groups, 'facets': result.get('availableFilterGroups') or [],
            'partial': any(isinstance(g['total'], int) and g['returned'] < g['total'] for g in groups)}

class GraphQLClient:
    def __init__(self, delay=2.0, cache_dir=Path('data/raw/graphql')):
        self.delay = max(1.5, delay)
        self.cache_dir = Path(cache_dir)
        self.last_request = 0
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'BokhyllanStockholm/0.2 (+https://github.com/njg017/stockholm-book-shelf)'})

    def search(self, author=None, query='', rows=100, start=0, filters=None):
        if not 1 <= rows <= 900:
            raise ValueError('rows must be between 1 and 900')
        if start < 0:
            raise ValueError('start must be zero or positive')
        request_filters = {'query': query, 'rows': rows}
        if start:
            request_filters['start'] = start
        if author:
            request_filters['author'] = [author]
        if filters:
            for key in ('language', 'yearPublishedSpan', 'genre', 'subject'):
                value = filters.get(key)
                if value:
                    request_filters[key] = value if isinstance(value, list) else [value]
        request = {'query': QUERY, 'variables': {'filterQuery': request_filters, '__operation': 'search'}, 'operationName': 'searchWithFilter'}
        time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        try:
            response = self.session.post(BASE + '/graphql', json=request, timeout=30)
        finally:
            self.last_request = time.monotonic()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(json.dumps(request_filters, sort_keys=True).encode()).hexdigest()[:16]
        cached = {'request': request, 'status': response.status_code, 'url': response.url,
                  'fetched_at': datetime.now(timezone.utc).isoformat(), 'body': response.text}
        (self.cache_dir / f'{digest}.json').write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding='utf-8')
        response.raise_for_status()
        result = parse_response(response.json())
        for book in result['books']:
            book['updated_at'] = cached['fetched_at']
        return result
