"""Inspect anonymous public catalogue traffic; do not log cookies or auth headers."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

OUT = Path('diagnostics/browser')

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def summarize_search_response(payload):
    result = ((payload.get('data') or {}).get('searchWithFilter') or {})
    groups = []
    for group in result.get('groupedMedia') or []:
        media = group.get('mediaList') or []
        groups.append({'media_type': group.get('mediaTypeEnum'), 'name': group.get('name'),
                       'num_found': group.get('numFound'), 'returned': len(media),
                       'first_id': media[0].get('key') if media else None,
                       'last_id': media[-1].get('key') if media else None})
    interesting = {}
    def walk(value, path=''):
        if isinstance(value, dict):
            for key, item in value.items():
                child = f'{path}.{key}' if path else key
                if any(token in key.lower() for token in ('cursor', 'next', 'token', 'page', 'start')):
                    interesting[child] = item if not isinstance(item, (dict, list)) else ('complex', type(item).__name__)
                walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value[:20]):
                walk(item, f'{path}[{index}]')
    walk(payload)
    return {'top_level_keys': list(payload), 'result_keys': list(result), 'groups': groups,
            'pagination_related': interesting}

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    traffic, failures, errors, pending = [], [], [], set()
    search_responses = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(locale='sv-SE')
        page = await context.new_page()

        async def capture(response):
            request = response.request
            if request.resource_type not in ('fetch', 'xhr'):
                return
            host = urlsplit(response.url).hostname or ''
            if any(word in host for word in ('piwik', 'google-analytics', 'doubleclick')):
                return
            index = len(traffic) + 1
            row = {'url': response.url, 'method': request.method, 'request_body': request.post_data, 'status': response.status, 'content_type': response.headers.get('content-type', '')}
            traffic.append(row)
            try:
                raw = await response.body()
                row['bytes'] = len(raw)
                if len(raw) <= 5000000:
                    name = f'response-{index:03d}.txt'
                    (OUT / name).write_bytes(raw)
                    row['body_file'] = name
                    try:
                        payload = json.loads(raw)
                        save(f'response-{index:03d}.json', payload)
                        row['json_keys'] = list(payload) if isinstance(payload, dict) else {'array_length': len(payload) if isinstance(payload, list) else None}
                        if 'searchWithFilter' in (request.post_data or ''):
                            search_responses.append({'index': index, 'request_body': request.post_data, 'summary': summarize_search_response(payload)})
                    except (ValueError, UnicodeError):
                        pass
                print(json.dumps(row, ensure_ascii=False))
            except Exception as exc:
                row['body_error'] = str(exc)

        def queue(response):
            task = asyncio.create_task(capture(response))
            pending.add(task)
            task.add_done_callback(pending.discard)

        page.on('response', queue)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('requestfailed', lambda request: failures.append({'url': request.url, 'failure': request.failure}))
        url = 'https://biblioteket.stockholm.se/sok?' + urlencode({'text': ''})
        links = []
        pagination = {'clicked': False, 'control': None, 'candidates': [], 'final_url': None}
        problem = None
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            try:
                await page.locator('a[href*="/titel/"]').first.wait_for(state='attached', timeout=30000)
            except PlaywrightTimeout:
                errors.append('No /titel/ anchor appeared within 30 seconds')
            await page.wait_for_timeout(5000)
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(3000)
            links_before = await page.locator('a[href*="/titel/"]').count()
            links = await page.locator('a[href*="/titel/"]').evaluate_all('(elements) => elements.map(a => ({href:a.href,text:a.textContent}))')
            candidates = await page.evaluate('''() => {
              const terms = ['nästa', 'fler', 'visa fler', 'vidare', 'next'];
              const nodes = Array.from(document.querySelectorAll('button, a[role="button"], a, nav button, nav a'));
              return nodes.map((element, index) => {
                const text = (element.textContent || '').trim();
                const aria = element.getAttribute('aria-label') || '';
                const title = element.getAttribute('title') || '';
                const lower = (text + ' ' + aria + ' ' + title).toLowerCase();
                const matches = terms.some(term => lower.includes(term));
                const inNav = !!element.closest('nav');
                if (!matches && !inNav) return null;
                const rect = element.getBoundingClientRect();
                return {index, tag: element.tagName, text, aria, title, href: element.href || null,
                        disabled: element.disabled || element.getAttribute('aria-disabled') === 'true',
                        visible: rect.width > 0 && rect.height > 0,
                        selector: element.tagName.toLowerCase() + (element.id ? '#' + element.id : '') + (element.className ? '.' + String(element.className).trim().split(/\s+/).join('.') : '')};
              }).filter(Boolean);
            }''')
            pagination['candidates'] = candidates
            clickable = [item for item in candidates if item.get('visible') and not item.get('disabled')]
            preferred = [item for item in clickable if any(term in ((item.get('text') or '') + ' ' + (item.get('aria') or '')).lower() for term in ('nästa', 'next', 'fler', 'vidare'))]
            chosen = preferred[0] if preferred else (clickable[0] if clickable else None)
            if chosen:
                control = page.locator(chosen['selector']).first
                pagination['control'] = chosen
                before = len(traffic)
                await control.click()
                await page.wait_for_timeout(10000)
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(3000)
                links_after = await page.locator('a[href*="/titel/"]').count()
                pagination['clicked'] = True
                pagination['requests_after_click'] = len(traffic) - before
                pagination['title_links_before'] = links_before
                pagination['title_links_after'] = links_after
            else:
                errors.append('No clickable pagination candidate was found')
            pagination['final_url'] = page.url
        except Exception as exc:
            problem = str(exc)
            errors.append(problem)
        finally:
            try:
                (OUT / 'rendered.html').write_text(await page.content(), encoding='utf-8')
                await page.screenshot(path=str(OUT / 'page.png'), full_page=True, timeout=15000)
            except Exception as exc:
                errors.append('Page snapshot: ' + str(exc))
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
            save('network.json', traffic)
            save('failed-requests.json', failures)
            save('errors.json', errors)
            save('title-links.json', links)
            save('pagination.json', pagination)
            save('search-responses.json', search_responses)
            summary = {'requested_url': url, 'final_url': page.url, 'fetch_xhr_responses': len(traffic), 'title_links': len(links), 'pagination': pagination, 'search_responses': search_responses, 'navigation_error': problem}
            save('summary.json', summary)
            print('SUMMARY', json.dumps(summary, ensure_ascii=False))
            print('ERRORS', json.dumps(errors, ensure_ascii=False))
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
                    f.write('## Browser network inspection\n```json\n' + json.dumps(summary, indent=2) + '\n```\nSee browser-network artifact for full evidence.\n')
            await browser.close()
        if problem:
            raise RuntimeError(problem)

if __name__ == '__main__':
    asyncio.run(main())
