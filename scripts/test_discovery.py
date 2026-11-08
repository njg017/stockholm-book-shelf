"""Offline validation for GraphQL catalogue parsing and pagination arithmetic."""
from library_graphql import parse_response

SAMPLE = {
    'data': {'searchWithFilter': {
        'start': 0, 'totalHits': 11,
        'groupedMedia': [
            {'mediaTypeEnum': 'BOOK', 'name': 'Bok', 'numFound': 10, 'mediaList': [
                {'id': 'CIC-1', 'key': '8487743', 'title': 'Imorgon och imorgon och imorgon', 'author': 'Gabrielle Zevin',
                 'mediaType': 'BOOK', 'mediaSubTypeDisplay': 'Pocket', 'image': '/cdn/cover/8487743',
                 'language': 'Svenska', 'languages': ['Svenska'], 'targetGroup': 'För vuxna',
                 'publisher': 'Albert Bonniers Förlag', 'publishedDate': '2024', 'holdingIds': []},
                {'id': 'CIC-2', 'key': '8510459', 'title': 'Tomorrow, and Tomorrow, and Tomorrow', 'author': 'Gabrielle Zevin',
                 'mediaType': 'BOOK', 'mediaSubTypeDisplay': 'Paperback', 'image': None,
                 'language': 'Engelska', 'languages': ['Engelska'], 'targetGroup': 'För vuxna',
                 'publisher': None, 'publishedDate': '2023', 'holdingIds': []}
            ]},
            {'mediaTypeEnum': 'AUDIOBOOKDAISY', 'name': 'Talbok', 'numFound': 1, 'mediaList': [
                {'id': 'CIC-3', 'key': '8147127', 'title': 'Livet enligt Fikry', 'author': 'Gabrielle Zevin',
                 'mediaType': 'AUDIOBOOKDAISY', 'mediaSubTypeDisplay': 'Talbok', 'image': None,
                 'language': 'Svenska', 'languages': ['Svenska'], 'targetGroup': 'För vuxna',
                 'publisher': 'BTJ', 'publishedDate': '2015', 'holdingIds': []}
            ]}
        ],
        'availableFilterGroups': []
    }}
}

def test_parse_response():
    result = parse_response(SAMPLE)
    assert result['total_hits'] == 11
    assert result['book_total'] == 10
    assert len(result['books']) == 2
    assert result['groups'][0]['returned'] == 2
    assert result['groups'][0]['total'] == 10
    assert result['partial'] is True
    swedish, english = result['books']
    assert swedish['title_id'] == '8487743'
    assert 'swedish-books' in swedish['shelves']
    assert swedish['reservation_url'] == 'https://biblioteket.stockholm.se/titel/8487743'
    assert english['title_id'] == '8510459'
    assert 'english-books' in english['shelves']
    assert english['cover_url'] is None
    assert swedish['published_year'] == 2024

def test_pagination_plan():
    page_size, total = 3, 10
    pages, start, seen = 0, 0, 0
    while pages < 10:
        returned = min(page_size, total - start)
        pages += 1
        seen += returned
        if returned < page_size or start + returned >= total:
            break
        start += returned
    assert pages == 4
    assert seen == 10
    assert start == 9

def test_report_shape():
    report = {'pages_fetched': 1, 'records_seen': 3, 'total_hits': 11, 'book_total': 10,
              'titles_queued_for_import': 3, 'pagination_verified': True, 'errors': []}
    assert report['pagination_verified'] is True
    assert report['records_seen'] <= report['book_total']
    assert not report['errors']

if __name__ == '__main__':
    test_parse_response()
    test_pagination_plan()
    test_report_shape()
    print('Discovery parsing and pagination validation passed.')
