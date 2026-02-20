from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from app.models.schemas import (
    CookiesInput,
    Subreddit,
    Post,
    Comment,
    SubredditSearchResult,
    SearchResult,
    CommentCreate,
)
from app.services.reddit_client import RedditClient

router = APIRouter()

_client: Optional[RedditClient] = None


async def get_client() -> RedditClient:
    global _client
    if _client is None:
        raise HTTPException(
            status_code=400, detail="Client not initialized. Call /auth/login first."
        )
    return _client


@router.post("/auth/login")
async def login(cookies: CookiesInput):
    global _client
    if _client:
        await _client.close()

    _client = RedditClient()
    await _client.initialize(cookies.cookies)

    is_auth = await _client.is_authenticated()
    if not is_auth:
        await _client.close()
        _client = None
        raise HTTPException(
            status_code=401, detail="Authentication failed. Please check your cookies."
        )

    return {"status": "authenticated", "message": "Successfully logged in to Reddit"}


@router.post("/auth/logout")
async def logout():
    global _client
    if _client:
        await _client.close()
        _client = None
    return {"status": "logged_out"}


@router.get("/auth/status")
async def auth_status():
    global _client
    if _client is None:
        return {"authenticated": False}
    is_auth = await _client.is_authenticated()
    return {"authenticated": is_auth}


@router.get("/search/subreddits", response_model=SubredditSearchResult)
async def search_subreddits(
    query: str, limit: int = 10, client: RedditClient = Depends(get_client)
):
    return await client.search_subreddits(query, limit)


@router.get("/search/posts", response_model=SearchResult)
async def search_posts(
    query: str,
    subreddit: Optional[str] = None,
    limit: int = 25,
    client: RedditClient = Depends(get_client),
):
    return await client.search_posts(query, subreddit, limit)


@router.get("/r/{subreddit}/comments/{post_id}", response_model=Post)
async def get_post(
    subreddit: str, post_id: str, client: RedditClient = Depends(get_client)
):
    post = await client.get_post(subreddit, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/r/{subreddit}/comments/{post_id}/comments", response_model=list[Comment])
async def get_comments(
    subreddit: str,
    post_id: str,
    limit: int = 50,
    client: RedditClient = Depends(get_client),
):
    return await client.get_comments(subreddit, post_id, limit)


@router.post("/r/{subreddit}/comments/{post_id}/comment")
async def add_comment(
    subreddit: str,
    post_id: str,
    comment: CommentCreate,
    client: RedditClient = Depends(get_client),
):
    success = await client.add_comment(
        subreddit, post_id, comment.text, comment.parent_id
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add comment")
    return {"status": "success", "message": "Comment added successfully"}
