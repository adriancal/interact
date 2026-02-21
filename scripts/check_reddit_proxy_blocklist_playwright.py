#!/usr/bin/env python3
import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright

PROXY_FILE = Path('/home/adrcal/.openclaw/residentialproxy.txt')
OUT_JSON = Path('/home/adrcal/.openclaw/workspace/interact/scripts/proxy_check_report_playwright.json')
OUT_WORKING = Path('/home/adrcal/.openclaw/workspace/interact/scripts/working_proxies.txt')

UAS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]


def load_lines(limit=0):
    lines = [ln.strip() for ln in PROXY_FILE.read_text().splitlines() if ln.strip() and not ln.startswith('#')]
    random.shuffle(lines)
    return lines[:limit] if limit else lines


async def check_one(playwright, line):
    host, port, user, pwd = line.split(':', 3)
    proxy = {'server': f'http://{host}:{port}', 'username': user, 'password': pwd}
    browser = await playwright.chromium.launch(
        headless=True,
        proxy=proxy,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--disable-blink-features=AutomationControlled'],
    )
    try:
        context = await browser.new_context(
            user_agent=random.choice(UAS),
            viewport={'width': random.choice([1280, 1366, 1440]), 'height': random.choice([720, 768, 900])},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        await page.goto('https://www.reddit.com/', wait_until='domcontentloaded', timeout=25000)
        await asyncio.sleep(random.uniform(0.8, 1.8))
        html = (await page.content()).lower()
        title = (await page.title()).lower()
        blocked = ('blocked' in title) or ('<title>blocked' in html)
        challenge = ('whoa there, pardner' in html) or ('request blocked' in html)
        ok = (not blocked) and (not challenge)
        return {
            'proxy_line': line,
            'ok': ok,
            'blocked': blocked,
            'challenge': challenge,
            'title': title,
            'url': page.url,
            'reason': 'ok' if ok else ('blocked' if blocked else 'challenge')
        }
    except Exception as e:
        return {'proxy_line': line, 'ok': False, 'blocked': False, 'challenge': False, 'title': '', 'url': '', 'reason': f'error:{type(e).__name__}'}
    finally:
        await browser.close()


async def main(limit=200, sleep_ms=350):
    lines = load_lines(limit=limit)
    results = []
    working = []
    print(f'Checking {len(lines)} proxies with Playwright...')
    async with async_playwright() as p:
        for i, line in enumerate(lines, 1):
            res = await check_one(p, line)
            results.append(res)
            if res['ok']:
                working.append(line)
            if i % 20 == 0 or i == len(lines):
                blocked = sum(1 for r in results if r['reason'] == 'blocked')
                chall = sum(1 for r in results if r['reason'] == 'challenge')
                errs = sum(1 for r in results if r['reason'].startswith('error:'))
                print(f"{i}/{len(lines)} checked | working={len(working)} | blocked={blocked} | challenge={chall} | errors={errs}")
            await asyncio.sleep(sleep_ms / 1000.0)

    OUT_JSON.write_text(json.dumps({'checked': len(results), 'working': len(working), 'results': results}, indent=2))
    OUT_WORKING.write_text('\n'.join(working) + ('\n' if working else ''))
    print(f'Saved: {OUT_JSON}')
    print(f'Saved: {OUT_WORKING} ({len(working)} working)')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=200)
    ap.add_argument('--sleep-ms', type=int, default=350)
    args = ap.parse_args()
    asyncio.run(main(limit=args.limit, sleep_ms=args.sleep_ms))
