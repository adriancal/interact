#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import requests

BASE_URL = "http://127.0.0.1:8000/api"
COOKIES_PATH = Path(__file__).resolve().parents[1] / "cookies.json"


def sanitize_cookie(c: dict) -> dict | None:
    name = c.get("name")
    value = c.get("value")
    domain = c.get("domain")
    path = c.get("path", "/")
    if not name or value is None or not domain:
        return None

    # Keep only reddit cookies
    if "reddit.com" not in domain:
        return None

    # Fix malformed domain variants
    if domain == ".www.reddit.com":
        domain = "www.reddit.com"

    out = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "secure": bool(c.get("secure", False)),
        "httpOnly": bool(c.get("httpOnly", False)),
    }

    # Playwright expects 'expires' as unix seconds (int), not expirationDate float
    exp = c.get("expirationDate")
    if exp:
        try:
            out["expires"] = int(exp)
        except Exception:
            pass

    return out


def load_cookies_payload(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    cleaned = []
    for c in raw:
        sc = sanitize_cookie(c)
        if sc:
            cleaned.append(sc)
    return cleaned


def call(method: str, path: str, **kwargs):
    r = requests.request(method, f"{BASE_URL}{path}", timeout=60, **kwargs)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body


def short_posts(posts: list[dict], n=3):
    for p in posts[:n]:
        print(f"  - [{p.get('subreddit')}] {p.get('title')} (id={p.get('id')})")


def main():
    if not COOKIES_PATH.exists():
        print(f"ERROR: missing {COOKIES_PATH}")
        return 1

    cookies = load_cookies_payload(COOKIES_PATH)
    print(f"Loaded {len(cookies)} sanitized cookies")

    code, body = call("POST", "/auth/login", json={"cookies": cookies})
    print(f"LOGIN: {code}")
    print(body)
    if code != 200:
        return 2

    # Discover parenting subreddits
    code, body = call("GET", "/search/subreddits", params={"query": "parenting", "limit": 10})
    print(f"\nSUBREDDITS: {code}")
    if code == 200:
        subs = body.get("subreddits", [])
        for s in subs[:10]:
            print(f"  - r/{s.get('name')} ({s.get('display_name')})")
    else:
        print(body)

    # Find topical posts
    queries = [
        ("Parenting", "toddler tantrum"),
        ("daddit", "self aware"),
        ("toddlers", "sleep regression"),
        ("raisingkids", "discipline"),
    ]

    best_candidate = None
    print("\nPOST CANDIDATES:")
    for sub, q in queries:
        code, body = call("GET", "/search/posts", params={"query": q, "subreddit": sub, "limit": 5})
        print(f"\n{sub} / '{q}' -> {code}")
        if code != 200:
            print(body)
            continue

        posts = body.get("posts", [])
        short_posts(posts, n=3)
        if posts and not best_candidate:
            best_candidate = posts[0]

    if best_candidate:
        print("\nBEST TEST POST:")
        print(json.dumps(best_candidate, indent=2, ensure_ascii=False))
        print("\nSUGGESTED TEST COMMENT (short, truthful):")
        print(
            "that sounds exhausting. one thing that helped us was naming the feeling first and only then setting a clear boundary. not magic, but it reduced the spiral a lot."
        )
    else:
        print("\nNo post candidates found.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
