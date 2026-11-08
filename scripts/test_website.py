"""Browser smoke test of repository files, not GitHub Pages deployment."""
import functools
import http.server
import json
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'diagnostics/website'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    books = json.loads((ROOT / 'data/books.json').read_text(encoding='utf-8'))
    assert books, 'No published books to test'
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors, checks = [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}/', wait_until='networkidle')
                expect(page.locator('#data-status')).to_contain_text(f'{len(books)} imported catalogue records')
                expect(page.locator('.book-card').first).to_be_visible()
                expect(page.locator('#book-modal')).to_be_hidden()
                checks.append('Real JSON loaded; cards rendered; modal initially hidden')
                page.screenshot(path=str(OUT / 'desktop.png'), full_page=True)
                page.locator('.book-card').first.click()
                expect(page.locator('#book-modal')).to_be_visible()
                assert page.locator('#modal-title').inner_text()
                expect(page.locator('#modal-updated')).to_contain_text('Availability checked:')
                href = page.locator('#modal-reserve').get_attribute('href')
                assert href and href.startswith('https://biblioteket.stockholm.se/titel/')
                page.screenshot(path=str(OUT / 'book-details.png'), full_page=True)
                page.keyboard.press('Escape')
                expect(page.locator('#book-modal')).to_be_hidden()
                checks.append('Details, official catalogue link and Escape close work')
                page.locator('#search').fill('no-match-7fe316')
                expect(page.locator('#empty-state')).to_be_visible()
                expect(page.locator('.book-card')).to_have_count(0)
                page.locator('#search').fill('')
                expect(page.locator('.book-card').first).to_be_visible()
                checks.append('Search empty state and reset work')
                for select in ('language', 'genre', 'branch'):
                    values = page.locator(f'#{select} option').evaluate_all('(els) => els.map(e => e.value).filter(Boolean)')
                    if values:
                        page.locator(f'#{select}').select_option(values[0])
                        expect(page.locator('.book-card').first).to_be_visible()
                        page.locator(f'#{select}').select_option('')
                checks.append('Populated dropdown filters return results')
                page.locator('#available-only').check()
                for badge in page.locator('.badge').all_text_contents():
                    assert badge.endswith(' available') and not badge.startswith('None')
                page.locator('#available-only').uncheck()
                page.set_viewport_size({'width': 390, 'height': 844})
                page.screenshot(path=str(OUT / 'mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile horizontal page overflow'
                checks.append('Availability filter and mobile page-width check passed')
                assert not errors, errors
            finally:
                (OUT / 'results.json').write_text(json.dumps({'checks_passed': checks, 'javascript_errors': errors}, indent=2), encoding='utf-8')
                try:
                    page.screenshot(path=str(OUT / 'final-state.png'), full_page=True)
                    (OUT / 'rendered.html').write_text(page.content(), encoding='utf-8')
                finally:
                    browser.close()
    finally:
        server.shutdown()
    print(json.dumps({'result': 'passed', 'checks': checks}, indent=2))

if __name__ == '__main__':
    main()
