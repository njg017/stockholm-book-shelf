# Verified catalogue search integration

Run `python scripts/import_library.py --author "Gabrielle Zevin" --rows 3` or manually run Actions > Update library data. Download the graphql-import artifact. This workflow does not commit generated data and is not scheduled while the integration is being validated.

The importer uses the browser-captured POST /graphql searchWithFilter operation. Books are selected from BOOK groups. Library keys identify separate catalogue records, not proven work-level identifiers. Covers are resolved from the library image field. English/Swedish shelves use returned language, never author nationality or seed shelf labels. No genre is inferred from language.

GraphQL errors and malformed records fail the search. Raw HTTP responses are saved before HTTP and GraphQL validation. If any seed fails or no books are returned, existing book and shelf files are retained; the report is still updated and the process exits nonzero.

Group totals and returned counts are reported separately. Pagination and larger rows values remain unverified. Partial results are labelled in the report, not represented as a complete catalogue.

ISBN, descriptions and availability are unknown until detail/holdings operations are captured. Search facet counts must not be treated as available copies. The HTML-based client and its old tests are legacy diagnostics, not the active importer. The front end still deliberately loads mock-books.json; switching it requires a separate field-mapping change.
