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

## Notes

- Reddit's UI structure may change, which could break selectors. Update selectors in `app/services/reddit_client.py` if needed.
- Use responsibly to avoid rate limiting.
- Some actions may require additional cookies or tokens depending on Reddit's current authentication requirements.
