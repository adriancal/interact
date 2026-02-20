from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CookiesInput(BaseModel):
    cookies: list[dict]


class Subreddit(BaseModel):
    name: str
    display_name: str
    subscribers: Optional[int] = None
    description: Optional[str] = None
    url: str


class Post(BaseModel):
    id: str
    title: str
    author: Optional[str] = None
    subreddit: str
    score: Optional[int] = None
    comments_count: Optional[int] = None
    created: Optional[datetime] = None
    url: str
    body: Optional[str] = None
    is_self: bool = True


class Comment(BaseModel):
    id: str
    author: Optional[str] = None
    body: str
    score: Optional[int] = None
    created: Optional[datetime] = None
    parent_id: Optional[str] = None
    depth: int = 0


class SearchResult(BaseModel):
    posts: list[Post]
    total: int
    query: str


class SubredditSearchResult(BaseModel):
    subreddits: list[Subreddit]
    total: int
    query: str


class CommentCreate(BaseModel):
    post_id: str
    text: str
    parent_id: Optional[str] = None
