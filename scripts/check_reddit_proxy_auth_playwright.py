#!/usr/bin/env python3
import argparse, asyncio, json, random
from pathlib import Path
from playwright.async_api import async_playwright

PROXY_FILE = Path('/home/adrcal/.openclaw/residentialproxy.txt')
COOKIES_FILE = Path('/home/adrcal/.openclaw/workspace/interact/cookies.json')
OUT_JSONL = Path('/home/adrcal/.openclaw/workspace/interact/scripts/proxy_auth_results.jsonl')
OUT_WORKING = Path('/home/adrcal/.openclaw/workspace/interact/scripts/working_proxies_auth.txt')

UAS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]

def load_lines():
    return [ln.strip() for ln in PROXY_FILE.read_text().splitlines() if ln.strip() and not ln.startswith('#')]

def load_cookies():
    raw = json.loads(COOKIES_FILE.read_text())
    out = []
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
            try:
                item['expires'] = int(c['expirationDate'])
            except Exception:
                pass
        out.append(item)
    return out

async def check(playwright, line, cookies, timeout_ms=12000):
    host, port, user, pwd = line.split(':', 3)
    proxy = {'server': f'http://{host}:{port}', 'username': user, 'password': pwd}
    browser = await playwright.chromium.launch(
        headless=True,
        proxy=proxy,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--disable-blink-features=AutomationControlled']
    )
    try:
        ctx = await browser.new_context(
            user_agent=random.choice(UAS),
            ignore_https_errors=True,
            viewport={'width': random.choice([1280,1366]), 'height': random.choice([720,768])}
        )
        for ck in cookies:
            try:
                await ctx.add_cookies([ck])
            except Exception:
                pass
        page = await ctx.new_page()
        await page.goto('https://www.reddit.com/', wait_until='domcontentloaded', timeout=timeout_ms)
        html = (await page.content()).lower()
        title = (await page.title()).lower()
        blocked = ('blocked' in title) or ('<title>blocked' in html) or ('whoa there, pardner' in html) or ('request has been blocked' in html)
        logged = ('alfredcali' in html) or ('logout' in html) or ('user menu' in html)
        has_login = ('log in' in html) or ('sign up' in html)
        ok = (not blocked) and (logged or not has_login)
        return {'proxy': line, 'ok': ok, 'blocked': blocked, 'logged': logged, 'has_login': has_login, 'title': title, 'url': page.url, 'reason': 'ok' if ok else ('blocked' if blocked else 'not_auth')}
    except Exception as e:
        return {'proxy': line, 'ok': False, 'blocked': False, 'logged': False, 'has_login': False, 'title': '', 'url': '', 'reason': f'error:{type(e).__name__}'}
    finally:
        await browser.close()

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--count', type=int, default=20)
    ap.add_argument('--sleep-ms', type=int, default=300)
    args = ap.parse_args()

    lines = load_lines()
    cookies = load_cookies()
    chunk = lines[args.start: args.start + args.count]
    print(f'chunk start={args.start} count={len(chunk)} total={len(lines)}')

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    working = []
    async with async_playwright() as p:
        for i, line in enumerate(chunk, 1):
            res = await check(p, line, cookies)
            with OUT_JSONL.open('a') as f:
                f.write(json.dumps(res) + '\n')
            if res['ok']:
                working.append(line)
            print(f"{i}/{len(chunk)} {line.split(':')[2]} -> {res['reason']}")
            await asyncio.sleep(args.sleep_ms / 1000)

    if working:
        with OUT_WORKING.open('a') as f:
            for w in working:
                f.write(w + '\n')
    print(f'chunk_done working={len(working)}')

if __name__ == '__main__':
    asyncio.run(main())
