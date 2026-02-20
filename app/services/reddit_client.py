from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from typing import Optional, Any
import asyncio
from datetime import datetime

from app.models.schemas import (
    Subreddit,
    Post,
    Comment,
    SubredditSearchResult,
    SearchResult,
)


class RedditClient:
    BASE_URL = "https://www.reddit.com"

    def __init__(self):
        self._playwright: Any = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def initialize(self, cookies: list[dict]):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        await self._context.add_cookies(cookies)
        self._page = await self._context.new_page()

    async def close(self):
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    def _get_page(self) -> Page:
        if not self._page:
            raise RuntimeError(
                "Client not initialized. Call initialize() with cookies first."
            )
        return self._page

    async def _wait_for_page_load(self):
        page = self._get_page()
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(1)

    async def search_subreddits(
        self, query: str, limit: int = 10
    ) -> SubredditSearchResult:
        page = self._get_page()
        search_url = f"{self.BASE_URL}/search/?type=sr&q={query}"
        await page.goto(search_url)
        await self._wait_for_page_load()
        await asyncio.sleep(3)

        subreddits = []
        subreddit_elements = await page.locator('a[href^="/r/"]').all()

        seen = set()
        for elem in subreddit_elements:
            if len(subreddits) >= limit:
                break
            try:
                href = await elem.get_attribute("href") or ""
                name = href.strip("/").replace("r/", "")
                if name in seen or "/" in name:
                    continue
                seen.add(name)
                display_name = await elem.inner_text()
                if display_name:
                    subreddits.append(
                        Subreddit(
                            name=name,
                            display_name=display_name,
                            url=f"{self.BASE_URL}{href}",
                        )
                    )
            except Exception:
                continue

        return SubredditSearchResult(
            subreddits=subreddits, total=len(subreddits), query=query
        )

    async def search_posts(
        self, query: str, subreddit: Optional[str] = None, limit: int = 25
    ) -> SearchResult:
        page = self._get_page()

        if subreddit:
            search_url = (
                f"{self.BASE_URL}/r/{subreddit}/search/?q={query}&restrict_sr=1"
            )
        else:
            search_url = f"{self.BASE_URL}/search/?q={query}&type=link"

        await page.goto(search_url)
        await self._wait_for_page_load()
        await asyncio.sleep(3)

        posts = []
        seen_ids = set()

        comment_links = await page.locator('a[href*="/comments/"]').all()

        for link in comment_links:
            if len(posts) >= limit:
                break
            try:
                href = await link.get_attribute("href") or ""
                parts = href.split("/comments/")
                if len(parts) < 2:
                    continue
                post_id = parts[1].split("/")[0]
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                title = await link.inner_text()
                if not title:
                    continue

                full_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

                subreddit_name = subreddit or "all"
                if not subreddit and len(parts[0].split("/r/")) > 1:
                    subreddit_name = parts[0].split("/r/")[-1].strip("/")

                posts.append(
                    Post(
                        id=post_id,
                        title=title,
                        subreddit=subreddit_name,
                        url=full_url,
                        is_self=True,
                    )
                )
            except Exception:
                continue

        return SearchResult(posts=posts, total=len(posts), query=query)

    async def _extract_post_from_element(self, elem, subreddit: str) -> Optional[Post]:
        try:
            post_id = await elem.get_attribute("id") or ""
            if post_id.startswith("t3_"):
                post_id = post_id[3:]

            title_elem = elem.locator('a[href*="/comments/"], h1, h3')
            title = (
                await title_elem.first.inner_text()
                if await title_elem.count() > 0
                else ""
            )

            link_elem = elem.locator('a[href*="/comments/"]')
            post_url = (
                await link_elem.first.get_attribute("href")
                if await link_elem.count() > 0
                else ""
            )

            if post_url and not post_url.startswith("http"):
                post_url = f"{self.BASE_URL}{post_url}"

            author_elem = elem.locator('a[href^="/user/"]')
            author = None
            if await author_elem.count() > 0:
                author_text = await author_elem.first.inner_text()
                author = author_text.replace("u/", "").strip()

            score_elem = elem.locator(
                '[data-testid="post-score"], shreddit-post-action-bar button[aria-label*="points"]'
            )
            score = None
            if await score_elem.count() > 0:
                score_text = await score_elem.first.inner_text()
                try:
                    score = int(
                        score_text.replace(",", "").replace("points", "").strip()
                    )
                except ValueError:
                    pass

            body_elem = elem.locator(
                '[data-testid="post-body"], div[data-click-id="body"]'
            )
            body = None
            if await body_elem.count() > 0:
                body = await body_elem.first.inner_text()

            return Post(
                id=post_id,
                title=title,
                author=author,
                subreddit=subreddit,
                score=score,
                url=post_url,
                body=body,
                is_self=True,
            )
        except Exception:
            return None

    async def get_post(self, subreddit: str, post_id: str) -> Optional[Post]:
        page = self._get_page()
        post_url = f"{self.BASE_URL}/r/{subreddit}/comments/{post_id}/"
        await page.goto(post_url)
        await self._wait_for_page_load()

        title_elem = page.locator(
            'shreddit-post h1, [data-testid="post-title"], h1[slot="title"]'
        )
        title = (
            await title_elem.first.inner_text() if await title_elem.count() > 0 else ""
        )

        author_elem = page.locator(
            'shreddit-post a[href^="/user/"], a[data-testid="post-author"]'
        )
        author = None
        if await author_elem.count() > 0:
            author_text = await author_elem.first.inner_text()
            author = author_text.replace("u/", "").strip()

        body_elem = page.locator(
            'shreddit-post div[data-testid="post-body"], div[data-click-id="body"]'
        )
        body = None
        if await body_elem.count() > 0:
            body = await body_elem.first.inner_text()

        score_elem = page.locator(
            'shreddit-post button[aria-label*="points"], [data-testid="post-score"]'
        )
        score = None
        if await score_elem.count() > 0:
            score_text = await score_elem.first.inner_text()
            try:
                score = int(score_text.replace(",", "").replace("points", "").strip())
            except ValueError:
                pass

        return Post(
            id=post_id,
            title=title,
            author=author,
            subreddit=subreddit,
            score=score,
            url=post_url,
            body=body,
            is_self=True,
        )

    async def get_comments(
        self, subreddit: str, post_id: str, limit: int = 50
    ) -> list[Comment]:
        page = self._get_page()
        post_url = f"{self.BASE_URL}/r/{subreddit}/comments/{post_id}/"
        await page.goto(post_url)
        await self._wait_for_page_load()
        await asyncio.sleep(2)

        comments = []
        comment_elements = await page.locator("shreddit-comment").all()

        for elem in comment_elements[:limit]:
            try:
                comment = await self._extract_comment_from_element(elem)
                if comment:
                    comments.append(comment)
            except Exception:
                continue

        return comments

    async def _extract_comment_from_element(self, elem) -> Optional[Comment]:
        try:
            thing_id = await elem.get_attribute("thingid") or ""
            if thing_id.startswith("t1_"):
                comment_id = thing_id[3:]
            else:
                comment_id = thing_id

            author = await elem.get_attribute("author")

            if not author:
                author_elem = elem.locator('a[href^="/user/"]')
                if await author_elem.count() > 0:
                    author = await author_elem.first.inner_text()

            body_elem = elem.locator("div[slot='comment-body'], md-div, .md")
            body = ""
            if await body_elem.count() > 0:
                body = await body_elem.first.inner_text()

            score_str = await elem.get_attribute("score")
            score = None
            if score_str:
                try:
                    score = int(score_str)
                except ValueError:
                    pass

            depth_str = await elem.get_attribute("depth")
            depth = 0
            if depth_str:
                try:
                    depth = int(depth_str)
                except ValueError:
                    pass

            return Comment(
                id=comment_id, author=author, body=body, score=score, depth=depth
            )
        except Exception:
            return None

    async def add_comment(
        self, subreddit: str, post_id: str, text: str, parent_id: Optional[str] = None
    ) -> bool:
        page = self._get_page()
        post_url = f"{self.BASE_URL}/r/{subreddit}/comments/{post_id}/"
        await page.goto(post_url)
        await self._wait_for_page_load()
        await asyncio.sleep(2)

        try:
            if parent_id:
                reply_btn = page.locator(
                    f"#{parent_id}, #t1_{parent_id}"
                ).first.locator("button:has-text('Reply')")
                if await reply_btn.count() > 0:
                    await reply_btn.click(force=True)
                    await asyncio.sleep(2)
            else:
                comment_composer = page.locator("comment-composer-host")
                if await comment_composer.count() > 0:
                    await comment_composer.first.click(force=True)
                    await asyncio.sleep(2)

            editor = page.locator("div[contenteditable='true']:visible")
            if await editor.count() > 0:
                await editor.first.click()
                await asyncio.sleep(0.3)
                await page.keyboard.type(text)
                await asyncio.sleep(0.5)

                submit = page.locator("button[type='submit']:visible")
                if await submit.count() > 0:
                    await submit.first.click()
                    await asyncio.sleep(3)
                    return True

            return False
        except Exception:
            return False

    async def is_authenticated(self) -> bool:
        page = self._get_page()
        await page.goto(self.BASE_URL)
        await self._wait_for_page_load()

        try:
            await page.wait_for_selector(
                'faceplate-dropdown-menu, faceplate-tracker[source="user_menu"]',
                timeout=5000,
            )
            return True
        except Exception:
            pass

        user_menu = page.locator(
            'faceplate-dropdown-menu, faceplate-tracker[source="user_menu"], [data-testid="user-dropdown"], button[aria-label="User menu"]'
        )
        if await user_menu.count() > 0:
            return True

        not_logged_in = page.locator('a[href*="login"], button:has-text("Log In")')
        return await not_logged_in.count() == 0
