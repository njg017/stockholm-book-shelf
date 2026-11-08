"""Observe an anonymous public title page without account actions."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path('diagnostics/title')

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    key = os.environ.get('TITLE_ID', '8487743')
    if not key.isascii() or not key.isdigit():
        raise ValueError('TITLE_ID must contain ASCII digits only')
    OUT.mkdir(parents=True, exist_ok=True)
    traffic, errors, failures = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale='sv-SE')
        page = context.new_page()

        def capture(response):
            request = response.request
            if request.resource_type not in ('xhr', 'fetch'):
                return
            if not response.url.startswith('https://biblioteket.stockholm.se/'):
                return
            row = {'url': response.url, 'method': request.method, 'status': response.status, 'content_type': response.headers.get('content-type', ''), 'request_body': request.post_data}
            traffic.append(row)
            index = len(traffic)
            try:
                body = response.body()
                row['bytes'] = len(body)
                if len(body) <= 5000000:
                    name = f'response-{index:03d}.txt'
                    (OUT / name).write_bytes(body)
                    row['body_file'] = name
                    try:
                        payload = json.loads(body)
                        save(f'response-{index:03d}.json', payload)
                        row['json_keys'] = list(payload) if isinstance(payload, dict) else None
                    except (ValueError, UnicodeError):
                        pass
            except Exception as exc:
                row['capture_error'] = str(exc)
            print(json.dumps(row, ensure_ascii=False), flush=True)

        page.on('response', capture)
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.on('requestfailed', lambda request: failures.append({'url': request.url, 'failure': request.failure}))
        problem = None
        url = f'https://biblioteket.stockholm.se/titel/{key}'
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(20000)
            (OUT / 'rendered.html').write_text(page.content(), encoding='utf-8')
            (OUT / 'visible-text.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
            page.screenshot(path=str(OUT / 'page.png'), full_page=True, timeout=15000)
        except Exception as exc:
            problem = str(exc)
            errors.append(problem)
        finally:
            save('network.json', traffic)
            save('errors.json', errors)
            save('failed-requests.json', failures)
            summary = {'title_id': key, 'requested_url': url, 'final_url': page.url, 'captured_responses': len(traffic), 'error': problem}
            save('summary.json', summary)
            print('SUMMARY', json.dumps(summary), flush=True)
            print('ERRORS', json.dumps(errors), flush=True)
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
                    f.write('## Title metadata capture\n```json\n' + json.dumps(summary, indent=2) + '\n```\nDownload the title-metadata artifact for response bodies.\n')
            browser.close()
        if problem:
            raise RuntimeError(problem)

if __name__ == '__main__':
    main()
