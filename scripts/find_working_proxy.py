#!/usr/bin/env python3
import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright

_REPO_ROOT = Path(__file__).resolve().parent.parent
PROXY_FILE = _REPO_ROOT / 'residentialproxy.txt'
COOKIES_FILE = _REPO_ROOT / 'cookies.json'
OUT_FILE = _REPO_ROOT / 'scripts' / 'working_proxy.json'

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.185 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.224 Safari/537.36',
]


def load_cookies():
    raw = json.loads(COOKIES_FILE.read_text())
    cleaned = []
    for c in raw:
        d = c.get('domain')
        if not d or 'reddit.com' not in d:
            continue
        if d == '.www.reddit.com':
            d = 'www.reddit.com'
        item = {
            'name': c['name'],
            'value': c['value'],
            'domain': d,
            'path': c.get('path', '/'),
            'secure': bool(c.get('secure', False)),
            'httpOnly': bool(c.get('httpOnly', False)),
        }
        if c.get('expirationDate'):
            item['expires'] = int(c['expirationDate'])
        cleaned.append(item)
    return cleaned


def load_proxies():
    lines = [ln.strip() for ln in PROXY_FILE.read_text().splitlines() if ln.strip() and not ln.startswith('#')]
    random.shuffle(lines)
    return lines


async def test_proxy(playwright, line, cookies):
    host, port, user, pwd = line.split(':', 3)
    proxy = {'server': f'http://{host}:{port}', 'username': user, 'password': pwd}
    browser = await playwright.chromium.launch(headless=True, proxy=proxy, args=['--no-sandbox'])
    try:
        context = await browser.new_context(
            ignore_https_errors=True,
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': random.choice([1280, 1366, 1440]), 'height': random.choice([720, 768, 900])},
        )
        for c in cookies:
            try:
                await context.add_cookies([c])
            except Exception:
                pass
        page = await context.new_page()
        await page.goto('https://www.reddit.com', wait_until='domcontentloaded', timeout=25000)
        await asyncio.sleep(random.uniform(0.8, 2.2))
        html = (await page.content()).lower()
        title = (await page.title()).lower()
        blocked = ('blocked' in title) or ('<title>blocked' in html)
        logged = ('alfredcali' in html) or ('logout' in html) or ('user menu' in html)
        has_login = ('log in' in html) or ('sign up' in html)
        return {
            'ok': (not blocked) and (logged or not has_login),
            'blocked': blocked,
            'logged': logged,
            'has_login': has_login,
            'title': title,
            'proxy': proxy,
        }
    finally:
        await browser.close()


async def main():
    cookies = load_cookies()
    proxies = load_proxies()[:500]
    print(f'testing {len(proxies)} proxies...')
    async with async_playwright() as p:
        for i, line in enumerate(proxies, 1):
            try:
                result = await test_proxy(p, line, cookies)
                if result['ok']:
                    OUT_FILE.write_text(json.dumps(result['proxy'], indent=2))
                    print(f"FOUND working proxy at #{i}: {result['proxy']['username']}")
                    return
            except Exception:
                pass

            # Human-like pacing between proxy attempts
            await asyncio.sleep(random.uniform(0.6, 1.8))

            if i % 25 == 0:
                print(f'checked {i}')
    print('no working proxy found in first 500')


if __name__ == '__main__':
    asyncio.run(main())
