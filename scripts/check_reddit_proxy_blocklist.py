#!/usr/bin/env python3
"""
Check every proxy in residentialproxy.txt and classify as blocked/unblocked for Reddit.

Proxy format expected per line:
  host:port:username:password

Output:
- JSON report with per-proxy results
- Optional text file with only working proxies

Usage:
  python check_reddit_proxy_blocklist.py \
    --proxy-file /home/adrcal/.openclaw/residentialproxy.txt \
    --out-json /home/adrcal/.openclaw/workspace/interact/scripts/proxy_check_report.json \
    --out-working /home/adrcal/.openclaw/workspace/interact/scripts/working_proxies.txt
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

import requests


REDDIT_URL = "https://www.reddit.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass
class CheckResult:
    proxy_line: str
    ok: bool
    blocked: bool
    status_code: int | None
    reason: str
    elapsed_ms: int


def parse_proxy_line(line: str) -> str:
    host, port, user, pwd = line.split(":", 3)
    return f"http://{user}:{pwd}@{host}:{port}"


def is_blocked_html(text: str) -> bool:
    t = text.lower()
    return (
        "<title>blocked</title>" in t
        or "you've been blocked" in t
        or "whoa there, pardner" in t
        or "request blocked" in t
    )


def check_one(line: str, timeout: float = 20.0) -> CheckResult:
    start = time.time()
    proxy_url = parse_proxy_line(line)
    proxies = {"http": proxy_url, "https": proxy_url}

    try:
        r = requests.get(
            REDDIT_URL,
            headers={"User-Agent": USER_AGENT},
            proxies=proxies,
            timeout=timeout,
            allow_redirects=True,
        )

        blocked = is_blocked_html(r.text)
        ok = (r.status_code == 200) and (not blocked)
        reason = "ok" if ok else ("blocked" if blocked else f"http_{r.status_code}")

        return CheckResult(
            proxy_line=line,
            ok=ok,
            blocked=blocked,
            status_code=r.status_code,
            reason=reason,
            elapsed_ms=int((time.time() - start) * 1000),
        )

    except requests.exceptions.Timeout:
        return CheckResult(line, False, False, None, "timeout", int((time.time() - start) * 1000))
    except requests.exceptions.ProxyError:
        return CheckResult(line, False, False, None, "proxy_error", int((time.time() - start) * 1000))
    except requests.exceptions.SSLError:
        return CheckResult(line, False, False, None, "ssl_error", int((time.time() - start) * 1000))
    except Exception as e:
        return CheckResult(line, False, False, None, f"error:{type(e).__name__}", int((time.time() - start) * 1000))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy-file", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-working", default="")
    ap.add_argument("--sleep-ms", type=int, default=400, help="Pause between checks")
    ap.add_argument("--limit", type=int, default=0, help="Optional max proxies to check")
    args = ap.parse_args()

    proxy_file = Path(args.proxy_file)
    out_json = Path(args.out_json)
    out_working = Path(args.out_working) if args.out_working else None

    if not proxy_file.exists():
        print(f"Proxy file not found: {proxy_file}")
        return 1

    lines = [ln.strip() for ln in proxy_file.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    if args.limit > 0:
        lines = lines[: args.limit]

    print(f"Checking {len(lines)} proxies...")

    results: List[CheckResult] = []
    working: List[str] = []

    for i, line in enumerate(lines, 1):
        res = check_one(line)
        results.append(res)
        if res.ok:
            working.append(line)

        if i % 25 == 0 or i == len(lines):
            print(f"{i}/{len(lines)} checked | working={len(working)} | blocked={sum(1 for r in results if r.blocked)}")

        if args.sleep_ms > 0 and i < len(lines):
            time.sleep(args.sleep_ms / 1000.0)

    report = {
        "checked": len(results),
        "working": len(working),
        "blocked": sum(1 for r in results if r.blocked),
        "timeout": sum(1 for r in results if r.reason == "timeout"),
        "proxy_error": sum(1 for r in results if r.reason == "proxy_error"),
        "results": [asdict(r) for r in results],
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2))
    print(f"Saved JSON report: {out_json}")

    if out_working is not None:
        out_working.parent.mkdir(parents=True, exist_ok=True)
        out_working.write_text("\n".join(working) + ("\n" if working else ""))
        print(f"Saved working proxies: {out_working}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
