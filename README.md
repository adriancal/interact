# Reddit Interaction API

A FastAPI backend that programmatically interacts with Reddit through UI scraping using Playwright. This bypasses the need for a Reddit developer API account.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Run the server:
```bash
python run.py
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## Getting Reddit Cookies

1. Log in to Reddit in your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage > Cookies > `https://www.reddit.com`
4. Export cookies as JSON array. You can use a browser extension like "EditThisCookie" or manually extract them:

```json
[
  {"name": "reddit_session", "value": "...", "domain": ".reddit.com", "path": "/"},
  {"name": "token_v2", "value": "...", "domain": ".reddit.com", "path": "/"}
]
```

## API Endpoints

### Authentication

**POST /api/auth/login**
Authenticate with Reddit using cookies.

Request body:
```json
{
  "cookies": [
    {"name": "reddit_session", "value": "your_session_value", "domain": ".reddit.com", "path": "/"}
  ]
}
```

**POST /api/auth/logout** - Clear session

**GET /api/auth/status** - Check authentication status

### Search

**GET /api/search/subreddits?query=python&limit=10** - Search for subreddits

**GET /api/search/posts?query=fastapi&subreddit=python&limit=25** - Search posts (subreddit is optional)

### Posts & Comments

**GET /api/r/{subreddit}/comments/{post_id}** - Get a specific post

**GET /api/r/{subreddit}/comments/{post_id}/comments?limit=50** - Get comments for a post

**POST /api/r/{subreddit}/comments/{post_id}/comment** - Add a comment

Request body:
```json
{
  "post_id": "abc123",
  "text": "Your comment text here",
  "parent_id": null
}
```

Use `parent_id` to reply to a specific comment.

## Example Usage

```python
import requests

BASE_URL = "http://localhost:8000"

# Login
cookies = [{"name": "reddit_session", "value": "...", "domain": ".reddit.com", "path": "/"}]
response = requests.post(f"{BASE_URL}/api/auth/login", json={"cookies": cookies})

# Search subreddits
subreddits = requests.get(f"{BASE_URL}/api/search/subreddits?query=python").json()

# Search posts
posts = requests.get(f"{BASE_URL}/api/search/posts?query=fastapi&subreddit=python").json()

# Get post details
post = requests.get(f"{BASE_URL}/api/r/python/comments/abc123").json()

# Get comments
comments = requests.get(f"{BASE_URL}/api/r/python/comments/abc123/comments").json()

# Add comment
requests.post(
    f"{BASE_URL}/api/r/python/comments/abc123/comment",
    json={"post_id": "abc123", "text": "Great post!"}
)
```

## Posting Sequence (Current Working Flow)

This is the exact sequence now used for successful posting:

1. **Load cookies** from browser export JSON (`cookies.json`)
   - Keep only valid Reddit cookies (`reddit_session`, `token_v2`, `csrf_token`, etc.)
   - Sanitize domains (e.g. `.www.reddit.com` -> `www.reddit.com`)

2. **Pick proxy from known-good list**
   - Primary source: `scripts/working_proxies.txt` (Playwright-validated)
   - Fallback: full `/home/adrcal/.openclaw/residentialproxy.txt`

3. **Initialize browser context via Playwright**
   - Launch Chromium with selected residential proxy
   - Apply anti-bot-friendly browser args + realistic UA/viewport
   - Add sanitized cookies

4. **Authenticate**
   - `POST /api/auth/login` with cookie payload
   - Verify with `GET /api/auth/status`

5. **Find post candidates**
   - `GET /api/search/subreddits`
   - `GET /api/search/posts` for parenting topics
   - `GET /api/r/{subreddit}/comments/{post_id}` to validate target post

6. **Post comment**
   - `POST /api/r/{subreddit}/comments/{post_id}/comment`
   - Payload: `{ post_id, text, parent_id }`

7. **Verify comment exists**
   - `GET /api/r/{subreddit}/comments/{post_id}/comments`
   - Confirm text + author appear in returned comments

## Comment Writing Rules (Parenting)

When generating comments for parenting subreddits, apply these constraints:

- Do **not** write in first person (`I`, `my`, `we`, `our`).
- Do **not** mention personal children/family anecdotes (e.g., "my kid did this").
- Keep comments short: **1 paragraph maximum**.
- Tone: practical, calm, supportive.
- Style: advice aligned with established parenting practice (emotion labeling, clear boundaries, consistency), without name-dropping studies/books.
- Avoid AI-sounding buzzwords and filler.
- **Never comment more than once on the same post.**
- No product mentions in Phase 1.

Good example style:
"that sounds exhausting. one thing that can help is naming the feeling first, then setting a short clear boundary. not magic, but it can reduce the spiral over time."

## Notes

- Reddit's UI structure may change, which could break selectors. Update selectors in `app/services/reddit_client.py` if needed.
- Use responsibly to avoid rate limiting.
- Some actions may require additional cookies or tokens depending on Reddit's current authentication requirements.
- Proxy health by plain HTTP is not enough; browser-level checks are required for Reddit reliability.
