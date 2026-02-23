#!/usr/bin/env python3
import argparse
import json
import os
import random
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000/api"
ROOT = Path("/home/adrcal/.openclaw/workspace")
INTERACT = ROOT / "interact"
STATE_PATH = ROOT / "memory" / "reddit_state.json"
LOG_DIR = ROOT / "shared" / "reddit_kapi"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def ensure_api_up():
    try:
        r = requests.get("http://127.0.0.1:8000/", timeout=5)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    cmd = (
        "cd /home/adrcal/.openclaw/workspace/interact && "
        "source venv/bin/activate && "
        "nohup env REDDIT_PROXY_MAX_ATTEMPTS=8 "
        "uvicorn app.main:app --host 0.0.0.0 --port 8000 "
        ">/tmp/interact_api.log 2>&1 &"
    )
    subprocess.run(["bash", "-lc", cmd], check=False)

    for _ in range(8):
        time.sleep(1)
        try:
            r = requests.get("http://127.0.0.1:8000/", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    return False


def sanitize_cookies(raw):
    out = []
    for c in raw:
        d = c.get("domain")
        if not d or "reddit.com" not in d:
            continue
        if d == ".www.reddit.com":
            d = "www.reddit.com"
        item = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": d,
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)),
            "httpOnly": bool(c.get("httpOnly", False)),
        }
        exp = c.get("expirationDate") or c.get("expires")
        if exp:
            try:
                item["expires"] = int(exp)
            except Exception:
                pass
        if item["name"] and item["value"] is not None:
            out.append(item)
    return out


def login(cookies_file: Path = None):
    path = cookies_file if cookies_file else INTERACT / "cookies.json"
    raw = load_json(path, [])
    cookies = sanitize_cookies(raw)
    r = requests.post(f"{BASE}/auth/login", json={"cookies": cookies}, timeout=120)
    if r.status_code != 200:
        return False, f"auth_login_{r.status_code}"
    s = requests.get(f"{BASE}/auth/status", timeout=60)
    try:
        ok = s.status_code == 200 and s.json().get("authenticated") is True
    except Exception:
        ok = False
    return ok, ("ok" if ok else "auth_status_false")


QUERIES = [
    # Tantrums & meltdowns
    ("Parenting", "tantrum"),
    ("Mommit", "tantrum"),
    ("toddlers", "meltdown"),
    # Behavior & defiance
    ("toddlers", "biting"),
    ("Parenting", "hitting"),
    ("raisingkids", "back talk"),
    ("daddit", "defiance"),
    ("Mommit", "whining"),
    ("Parenting", "won't listen"),
    # Emotional regulation
    ("daddit", "self aware"),
    ("Parenting", "emotional regulation"),
    ("raisingkids", "anger"),
    # Sleep
    ("toddlers", "sleep regression"),
    ("Parenting", "bedtime"),
    ("Mommit", "night waking"),
    # Eating
    ("Parenting", "picky eater"),
    ("toddlers", "won't eat"),
    # School age (5–10)
    ("Parenting", "homework"),
    ("raisingkids", "screen time"),
    ("Parenting", "lying"),
    ("daddit", "anxiety"),
    ("Mommit", "separation anxiety"),
    ("Parenting", "sibling"),
    # Milestones
    ("raisingkids", "potty training"),
    ("toddlers", "regression"),
]


def fetch_candidates():
    """Pick a random query and fetch up to 6 valid candidates. Tries up to 3 queries."""
    from datetime import datetime, timedelta

    allowed = {"Parenting", "daddit", "toddlers", "raisingkids", "Mommit"}
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    query_pool = random.sample(QUERIES, min(3, len(QUERIES)))
    seen = set()
    out = []

    for sub, q in query_pool:
        r = requests.get(f"{BASE}/search/posts", params={"query": q, "subreddit": sub, "limit": 12}, timeout=90)
        if r.status_code != 200:
            continue

        for p in r.json().get("posts", []):
            pid = (p.get("id") or "").strip()
            psub = (p.get("subreddit") or "").strip()
            url = (p.get("url") or "")

            if psub not in allowed:
                continue
            if not pid or "?" in pid or not pid.isalnum():
                continue
            if "/comments/" not in url:
                continue
            if pid in seen:
                continue
            seen.add(pid)

            # Fetch post details for body enrichment and date filter
            try:
                post_resp = requests.get(f"{BASE}/r/{psub}/comments/{pid}", timeout=60)
                if post_resp.status_code == 200:
                    post_data = post_resp.json()
                    if post_data.get("body"):
                        p = {**p, "body": post_data["body"]}
                    created_str = post_data.get("created")
                    if created_str:
                        try:
                            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                            if created < one_week_ago:
                                continue
                        except Exception:
                            pass
            except Exception:
                pass

            out.append(p)
            if len(out) >= 6:  # enough candidates; stop immediately
                random.shuffle(out)
                return out

    random.shuffle(out)
    return out


def build_comment(title: str, body: str | None, subreddit: str) -> str:
    """Generate custom comment using LLM based on full post content."""
    import sys
    
    # Load NVIDIA_API_KEY from .env if not already in environment
    if not os.getenv("NVIDIA_API_KEY"):
        env_file = ROOT.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("NVIDIA_API_KEY="):
                    # Handle both 'value' and "value" formats
                    val = line.split("=", 1)[1].strip()
                    if (val.startswith("'") and val.endswith("'")) or \
                       (val.startswith('"') and val.endswith('"')):
                        val = val[1:-1]
                    os.environ["NVIDIA_API_KEY"] = val
                    break
    
    # Import from same directory
    try:
        from comment_generator import generate_comment
        return generate_comment(title, body, subreddit)
    except Exception as e:
        # Fallback to simple template if LLM fails
        t = (title or "").lower()
        if "tantrum" in t:
            return "that sounds tough. naming the emotion and keeping responses short and calm usually helps over time."
        if "sleep" in t:
            return "sleep phases are hard. a predictable routine usually matters more than any single trick."
        return "that sounds really tough. consistency and calm usually help, even when it feels slow."


def post_comment(sub: str, post_id: str, text: str):
    payload = {"post_id": post_id, "text": text, "parent_id": None}
    r = requests.post(f"{BASE}/r/{sub}/comments/{post_id}/comment", json=payload, timeout=120)
    return r.status_code, r.text


def already_commented_on_post(sub: str, post_id: str) -> bool:
    """Hard guard: never comment twice on same post."""
    try:
        r = requests.get(f"{BASE}/r/{sub}/comments/{post_id}/comments", params={"limit": 200}, timeout=120)
        if r.status_code != 200:
            return False
        comments = r.json()
        for c in comments:
            if c.get("author") == "AlfredCali":
                return True
    except Exception:
        pass
    return False


def verify_comment(sub: str, post_id: str, snippet: str):
    for _ in range(4):
        time.sleep(2)
        r = requests.get(f"{BASE}/r/{sub}/comments/{post_id}/comments", params={"limit": 120}, timeout=120)
        if r.status_code != 200:
            continue
        try:
            comments = r.json()
        except Exception:
            continue
        for c in comments:
            if c.get("author") == "AlfredCali" and snippet in (c.get("body") or "").lower():
                return True
    return False


def write_log(run_label, observed, target, comment, status, reason, log_dir=None):
    out_dir = log_dir if log_dir else LOG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"session_{ts}_interact_{run_label}.md"
    body_preview = (target.get("body") or "")[:300]
    if len(target.get("body") or "") > 300:
        body_preview += "..."
    path.write_text(
        "\n".join(
            [
                f"# Reddit Interact Run {run_label}",
                f"- Time: {now_iso()}",
                f"- Status: {status}",
                f"- Reason: {reason}",
                "",
                "## Observed Post",
                f"- r/{observed.get('subreddit','?')} · {observed.get('id','?')}",
                f"- {observed.get('title','')}",
                f"- {observed.get('url','')}",
                "",
                "## Target Post",
                f"- r/{target.get('subreddit','?')} · {target.get('id','?')}",
                f"- {target.get('title','')}",
                f"- {target.get('url','')}",
                *(([f"- Body: {body_preview}"] if body_preview else [])),
                "",
                "## Comment",
                comment or "",
            ]
        )
    )
    return str(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-label", required=True)
    ap.add_argument("--max-jitter-seconds", type=int, default=1800)
    ap.add_argument("--dry-run", action="store_true", help="Run the full flow but skip posting and state mutations")
    ap.add_argument("--cookies", type=Path, default=None, help="Path to cookies.json (overrides default workspace path)")
    ap.add_argument("--log-dir", type=Path, default=None, help="Directory for session log files (overrides default workspace path)")
    ap.add_argument("--state-path", type=Path, default=None, help="Path to reddit_state.json (overrides default workspace path)")
    args = ap.parse_args()

    random.seed()

    effective_state_path = args.state_path if args.state_path else STATE_PATH
    state = load_json(effective_state_path, {"status": "PAUSED", "sessions_log": []})
    today = datetime.now().strftime("%Y-%m-%d")
    daily = state.setdefault("daily", {})
    day = daily.setdefault(today, {"target": random.randint(4, 8), "done": 0})

    if not args.dry_run:
        if state.get("status") != "active":
            result = {"status": "skipped", "reason": "state_not_active", "run": args.run_label}
            print(json.dumps(result))
            return

        if day.get("done", 0) >= day.get("target", 4):
            result = {"status": "skipped", "reason": "quota_reached", "run": args.run_label, "done": day.get("done"), "target": day.get("target")}
            print(json.dumps(result))
            return

    # jitter: skipped entirely in dry-run mode
    max_jitter = 0 if args.dry_run else max(0, int(args.max_jitter_seconds))
    time.sleep(random.randint(0, max_jitter))

    if not ensure_api_up():
        print(json.dumps({"status": "error", "reason": "api_down", "run": args.run_label}))
        return

    ok, why = login(args.cookies)
    if not ok:
        print(json.dumps({"status": "error", "reason": why, "run": args.run_label}))
        return

    candidates = fetch_candidates()
    if len(candidates) < 2:
        print(json.dumps({"status": "error", "reason": "not_enough_posts", "run": args.run_label}))
        return

    observed = candidates[0]

    # step 2: observe one post comments only, then dwell like a human reader
    try:
        requests.get(
            f"{BASE}/r/{observed.get('subreddit')}/comments/{observed.get('id')}/comments",
            params={"limit": 30},
            timeout=120,
        )
    except Exception:
        pass
    time.sleep(random.uniform(20, 90))

    # step 3: post on a different candidate; retry up to 3 targets
    # hard dedupe: never comment twice on same post
    commented_keys = {
        f"{x.get('subreddit')}:{x.get('post_id')}"
        for x in state.get("sessions_log", [])
        if x.get("subreddit") and x.get("post_id")
    }

    attempts = []
    pool = [
        p for p in candidates[1:]
        if p.get("id") != observed.get("id")
        and f"{p.get('subreddit')}:{p.get('id')}" not in commented_keys
    ]
    random.shuffle(pool)
    max_post_attempts = min(3, len(pool))

    if max_post_attempts == 0:
        print(json.dumps({"status": "skipped", "reason": "no_new_posts_available", "run": args.run_label}))
        return

    success = None
    for target in pool[:max_post_attempts]:
        sub = target.get("subreddit")
        pid = target.get("id")

        # live dedupe check against Reddit comments
        if already_commented_on_post(sub, pid):
            attempts.append({
                "subreddit": sub,
                "post_id": pid,
                "title": target.get("title"),
                "code": "skip_already_commented",
            })
            continue

        comment = build_comment(target.get("title", ""), target.get("body"), target.get("subreddit"))

        if args.dry_run:
            attempts.append({
                "subreddit": sub,
                "post_id": pid,
                "title": target.get("title"),
                "code": "dry_run",
            })
            success = (target, comment, "dry_run")
            break

        code, body = post_comment(sub, pid, comment)
        attempts.append(
            {
                "subreddit": sub,
                "post_id": pid,
                "title": target.get("title"),
                "code": code,
            }
        )

        # skip archived/locked/low-karma/other failures and try next target
        if code != 200:
            time.sleep(random.uniform(1.0, 2.5))
            continue

        words = comment.split()
        mid = len(words) // 2
        snippet = " ".join(words[max(0, mid - 2):mid + 2]).strip('",. ').lower()
        verified = verify_comment(sub, pid, snippet)
        success = (target, comment, verified)
        break

    if not success:
        fallback_target = pool[0] if pool else {"subreddit": "?", "id": "?", "title": "?"}
        fallback_comment = build_comment(fallback_target.get("title", ""), fallback_target.get("body"), fallback_target.get("subreddit"))
        effective_log_dir = args.log_dir if args.log_dir else LOG_DIR
        log_path = write_log(args.run_label, observed, fallback_target, fallback_comment, "error", f"post_failed_after_{max_post_attempts}_attempts", log_dir=effective_log_dir)
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": f"post_failed_after_{max_post_attempts}_attempts",
                    "run": args.run_label,
                    "attempts": attempts,
                    "log": log_path,
                }
            )
        )
        return

    target, comment, verified = success

    if not args.dry_run:
        day["done"] = day.get("done", 0) + 1
        state.setdefault("sessions_log", []).append(
            {
                "time": now_iso(),
                "run": args.run_label,
                "status": "ok" if verified else "posted_unverified",
                "subreddit": target.get("subreddit"),
                "post_id": target.get("id"),
                "comment": comment,
                "attempts": attempts,
            }
        )
        save_json(effective_state_path, state)

    status = "dry_run" if args.dry_run else ("ok" if verified else "posted_unverified")
    effective_log_dir = args.log_dir if args.log_dir else LOG_DIR
    log_path = write_log(args.run_label, observed, target, comment, status, "done", log_dir=effective_log_dir)
    body_snippet = (target.get("body") or "")[:200] or None
    print(
        json.dumps(
            {
                "status": status,
                "dry_run": args.dry_run,
                "run": args.run_label,
                "observed": {
                    "subreddit": observed.get("subreddit"),
                    "id": observed.get("id"),
                    "title": observed.get("title"),
                    "url": observed.get("url"),
                },
                "post": {
                    "subreddit": target.get("subreddit"),
                    "id": target.get("id"),
                    "title": target.get("title"),
                    "url": target.get("url"),
                    "body": body_snippet,
                },
                "comment": comment,
                "done": day.get("done"),
                "target": day.get("target"),
                "attempts": attempts,
                "log": log_path,
            }
        )
    )


if __name__ == "__main__":
    main()
