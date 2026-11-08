"""Parse the observed title-page Next.js media object."""
import json
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from library_graphql import BASE, CatalogueError

def parse_title(html, expected_key):
    tag = BeautifulSoup(html, 'html.parser').find('script', id='__NEXT_DATA__')
    if tag is None:
        raise CatalogueError('Missing title __NEXT_DATA__')
    state = json.loads(tag.get_text())
    media = state.get('props', {}).get('pageProps', {}).get('media')
    if not isinstance(media, dict) or str(media.get('key')) != str(expected_key) or not media.get('title'):
        raise CatalogueError('Missing or mismatched title media record')
    isbns = media.get('isbn') or []
    if isinstance(isbns, str):
        isbns = [isbns]
    branches = media.get('holdings')
    if branches is not None and not isinstance(branches, list):
        raise CatalogueError('Unexpected holdings structure')
    normalized = None if branches is None else []
    seen = set()
    for branch in branches or []:
        identity = branch.get('branchId') or branch.get('id') or branch.get('name')
        if not identity or identity in seen:
            raise CatalogueError('Missing or duplicate branch identity')
        seen.add(identity)
        normalized.append({'branch_id': identity, 'branch': branch.get('name'),
            'slug': (branch.get('branch') or {}).get('slug'),
            'loan_status': branch.get('loanStatus'),
            'total_copies': branch.get('nofTotal'),
            'available_copies': branch.get('nofTotalAvailableForLoan'),
            'reservable': branch.get('reservable'),
            'reference_only': branch.get('referenceOnly'),
            'locations': branch.get('holdings')})
    def total(field):
        if normalized is None or not normalized:
            return None
        values = [b[field] for b in normalized]
        if not all(type(v) is int and v >= 0 for v in values):
            return None
        return sum(values)
    available = total('available_copies')
    all_known = normalized is not None and all(type(b['available_copies']) is int and b['available_copies'] >= 0 for b in normalized)
    subjects = media.get('subjects') or []
    return {'title_id': str(media['key']), 'title': media['title'], 'author': media.get('author'),
        'isbn': next((s for s in isbns if isinstance(s, str) and len(s) == 13), isbns[0] if isbns else None),
        'isbns': isbns, 'description': media.get('description'),
        'original_title': media.get('originalTitle'), 'original_language': media.get('originalLanguage'),
        'translators': media.get('translators'), 'page_count': media.get('pageCount'),
        'genres': media.get('genre') or [],
        'subjects': [s['subject'] for s in subjects if isinstance(s, dict) and s.get('subject')],
        'holdings': normalized, 'available_copies': available, 'total_copies': total('total_copies'),
        'available_branches': [b['branch'] for b in normalized if b['available_copies'] > 0] if all_known else None,
        'availability_status': 'unknown' if available is None else ('available' if available > 0 else 'unavailable'),
        'reservation_count': media.get('nofReservations'), 'reservable': media.get('isAllowedToReserve')}

def enrich_title(client, book):
    key = str(book['title_id'])
    if not key.isascii() or not key.isdigit():
        raise CatalogueError('Invalid title key')
    time.sleep(max(0, client.delay - (time.monotonic() - client.last_request)))
    try:
        response = client.session.get(f'{BASE}/titel/{key}', timeout=30)
    finally:
        client.last_request = time.monotonic()
    directory = client.cache_dir.parent / 'title-html'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f'{key}.html').write_text(response.text, encoding='utf-8')
    response.raise_for_status()
    details = parse_title(response.text, key)
    book.update(details)
    book['availability_checked_at'] = datetime.now(timezone.utc).isoformat()
    return book
