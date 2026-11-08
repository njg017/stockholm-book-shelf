"""Offline tests using minimal synthetic fixtures shaped like captured title state."""
import json
import unittest
from title_metadata import parse_title
from library_graphql import CatalogueError

def html(holdings=None, key='8487743'):
    media = {'key': key, 'title': 'Example title', 'isbn': ['9789100806439', '9100806439'], 'subjects': [{'subject': 'Tv-spel'}], 'holdings': holdings}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({'props': {'pageProps': {'media': media}}}) + '</script>'

class TitleTests(unittest.TestCase):
    def test_aggregate_branch_counts_not_nested_locations(self):
        rows = [{'branchId': str(i), 'name': str(i), 'nofTotal': total, 'nofTotalAvailableForLoan': available, 'holdings': [{'nofTotal': 999}]} for i, total, available in [(1, 4, 1), (2, 4, 1), (3, 3, 1)]]
        book = parse_title(html(rows), '8487743')
        self.assertEqual((book['total_copies'], book['available_copies']), (11, 3))
        self.assertEqual(book['isbn'], '9789100806439')
        self.assertEqual(book['subjects'], ['Tv-spel'])
    def test_missing_holdings_are_unknown(self):
        self.assertIsNone(parse_title(html(), '8487743')['available_copies'])
    def test_zero_available_is_not_unknown(self):
        book = parse_title(html([{'id': '1', 'nofTotal': 1, 'nofTotalAvailableForLoan': 0}]), '8487743')
        self.assertEqual(book['availability_status'], 'unavailable')
    def test_mismatched_edition_rejected(self):
        with self.assertRaises(CatalogueError):
            parse_title(html(key='8510459'), '8487743')

if __name__ == '__main__':
    unittest.main()
