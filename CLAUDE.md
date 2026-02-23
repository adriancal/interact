# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Install dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

**Run the API server (development):**
```bash
python run.py
# or directly:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Run the API server (production/background):**
```bash
REDDIT_PROXY_MAX_ATTEMPTS=8 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Test comment generation:**
```bash
NVIDIA_API_KEY=... python comment_generator.py "Post title here" "Optional body text" "subreddit"
```

**Run the cron session manually (no jitter):**
```bash
python reddit_cron_session.py --run-label test-001 --max-jitter-seconds 0
```

**Find working proxies:**
```bash
python scripts/find_working_proxy.py
```

**Lint:**
```bash
ruff check .
ruff format .
```

## Architecture

The system has two layers:

### 1. FastAPI Service (`app/`)
A stateful HTTP API that wraps a single shared Playwright browser session. All routes in `app/routes/reddit.py` share a global `_client: RedditClient` singleton that holds the active browser context. The session must be initialized via `POST /api/auth/login` with Reddit cookies before any other endpoints work.

- `app/main.py` — FastAPI app setup, mounts router at `/api`
- `app/routes/reddit.py` — Route handlers; the global `_client` is the core session state
- `app/services/reddit_client.py` — All Playwright browser automation logic
- `app/models/schemas.py` — Pydantic models for requests/responses

### 2. Cron Orchestrator (`reddit_cron_session.py`)
A standalone script that drives the full posting workflow by calling the FastAPI service over HTTP. It manages:
- Daily quota state persisted to `~/.openclaw/workspace/memory/reddit_state.json`
- Post deduplication (both in-memory state log and live Reddit comment check)
- The "observe one post, comment on a different one" pattern to appear organic
- Session logs written to `~/.openclaw/workspace/shared/reddit_kapi/`

The cron script self-starts the API server if it isn't running (via subprocess).

### 3. Comment Generator (`comment_generator.py`)
Calls the NVIDIA AI API (OpenAI-compatible) using model `z-ai/glm5`. Includes post-processing to strip AI vocabulary (two tiers of banned words). Falls back to template strings if the LLM call fails.

## Key Configuration

**Environment variables:**
- `REDDIT_NO_PROXY=1` — skip proxy entirely, use direct connection
- `REDDIT_PROXY_SERVER` / `REDDIT_PROXY_USER` / `REDDIT_PROXY_PASS` — explicit single proxy override
- `REDDIT_PROXY_MAX_ATTEMPTS` — how many proxies to try before failing (default: 20)
- `NVIDIA_API_KEY` — required for LLM comment generation; cron script auto-loads from `~/.openclaw/.env`

**External file paths (hardcoded to `/home/adrcal/.openclaw/`):**
- `workspace/interact/cookies.json` — Reddit session cookies (browser export format)
- `residentialproxy.txt` — full Webshare proxy list (`host:port:user:pass` per line)
- `workspace/interact/scripts/working_proxies.txt` — pre-vetted proxies (Playwright-validated, gitignored)

## Proxy Selection Logic

`RedditClient._proxy_candidates()` tries in priority order:
1. `REDDIT_NO_PROXY=1` → no proxy
2. `REDDIT_PROXY_SERVER` env var → single proxy
3. `scripts/working_proxies.txt` (pre-vetted)
4. `~/.openclaw/residentialproxy.txt` (full list)
5. Hardcoded Webshare fallback

On initialization, each proxy candidate is browser-tested against reddit.com before being accepted. A proxy is rejected if the page title contains "blocked" or shows Reddit's bot-block page.

## Reddit UI Selectors

Selectors in `reddit_client.py` target Reddit's new `shreddit-*` web components (the redesigned UI). If Reddit changes its frontend, update:
- `shreddit-post` — post element on post pages
- `shreddit-comment` — comment elements (uses `thingid` attribute for comment ID, `author` attribute for username)
- `comment-composer-host` — top-level comment input
- `faceplate-dropdown-menu` — user menu (used to detect authenticated state)

## State / Deduplication

`reddit_state.json` tracks:
- `status`: must be `"active"` for the cron to post (manual gate)
- `daily.<date>.target` / `.done`: per-day quota (4–8 comments, randomized at day start)
- `sessions_log`: array of all past posts with subreddit + post_id for deduplication

The cron script also does a live check (`already_commented_on_post`) that fetches the post's comments and looks for the account username before posting.
