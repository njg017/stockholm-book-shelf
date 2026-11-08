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

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    traffic, failures, errors, pending = [], [], [], set()
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
        pagination = {'clicked': False, 'control': None, 'final_url': None}
        problem = None
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            try:
                await page.locator('a[href*="/titel/"]').first.wait_for(state='attached', timeout=30000)
            except PlaywrightTimeout:
                errors.append('No /titel/ anchor appeared within 30 seconds')
            await page.wait_for_timeout(5000)
            links = await page.locator('a[href*="/titel/"]').evaluate_all('(elements) => elements.map(a => ({href:a.href,text:a.textContent}))')
            candidates = page.locator("button, a[role='button'], a").filter(has_text='Nästa')
            count = await candidates.count()
            if count:
                control = candidates.first
                pagination['control'] = await control.evaluate('element => ({tag: element.tagName, text: element.textContent?.trim(), href: element.href || null, aria: element.getAttribute("aria-label")})')
                before = len(traffic)
                await control.click()
                await page.wait_for_timeout(8000)
                pagination['clicked'] = True
                pagination['requests_after_click'] = len(traffic) - before
            else:
                errors.append('No pagination control containing Nästa was found')
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
            summary = {'requested_url': url, 'final_url': page.url, 'fetch_xhr_responses': len(traffic), 'title_links': len(links), 'pagination': pagination, 'navigation_error': problem}
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
