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
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Test comment generation:**
```bash
# Uses model cascade by default (gemini-2.0-flash-preview → gemini-2.5-pro → nvidia)
python comment_generator.py "Post title here" "Optional body text" "subreddit"

# Force a specific model: flash | pro | nvidia (or full model name)
python comment_generator.py "Post title here" --model flash
python comment_generator.py "Post title here" --model pro
python comment_generator.py "Post title here" --model nvidia
```

**Run the cron session manually (no jitter):**
```bash
python reddit_cron_session.py --run-label test-001 --max-jitter-seconds 0
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
- Daily quota state persisted to `data/reddit_state.json`
- Post deduplication (both in-memory state log and live Reddit comment check)
- The "observe one post, comment on a different one" pattern to appear organic
- Session logs written to `logs/`

The cron script self-starts the API server if it isn't running (via subprocess).

### 3. Comment Generator (`comment_generator.py`)
Tries models in cascade order: `gemini-2.0-flash-preview` → `gemini-2.5-pro` → `z-ai/glm5` (NVIDIA). Raises if all fail. Includes post-processing to strip AI vocabulary (two tiers of banned words); regenerates once with a stricter prompt if AI words are detected.

## Key Configuration

**Environment variables:**
- `GEMINI_API_KEY` — used for Gemini models (primary); cron script auto-loads from `.env`
- `NVIDIA_API_KEY` — used for NVIDIA fallback model; cron script auto-loads from `.env`

**Local file paths (all relative to repo root, gitignored):**
- `cookies.json` — Reddit session cookies (browser export format)
- `.env` — environment variables (e.g. `NVIDIA_API_KEY=...`)
- `data/reddit_state.json` — daily quota and session deduplication state
- `logs/` — per-run session markdown logs

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
