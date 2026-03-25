"""Reddit private API client using rnet (bypasses Cloudflare).

Provides methods for:
- User profiles and posts
- Subreddit posts
- Post details with comments
- Search posts
- Upvote/downvote
- Comment
- Submit posts
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote, urlencode

from rnet import Client as RnetClient, Emulation

REDDIT_BASE = "https://www.reddit.com"
OLD_REDDIT_BASE = "https://old.reddit.com"
OAUTH_BASE = "https://oauth.reddit.com"
# Use www.reddit.com for read operations (works with cookies)
API_BASE = "https://www.reddit.com"


class RedditAPIError(Exception):
    """Raised when Reddit API returns an error."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"Reddit API error {status}: {message}")


class RedditClient:
    """Async Reddit client powered by rnet (Cloudflare-safe)."""

    def __init__(self, language: str = "en-US"):
        self._rnet = RnetClient(emulation=Emulation.Chrome133)
        self._cookies: dict[str, str] = {}
        self._headers: dict[str, str] = {}
        self._language = language
        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"
        )

    # ── Cookie/Auth Management ───────────────────────────────────────────

    def load_cookies(self, path: str) -> None:
        """Load cookies from a JSON file."""
        raw = json.loads(Path(path).read_text())
        if isinstance(raw, list):
            self._cookies = {c["name"]: c["value"] for c in raw}
        else:
            self._cookies = dict(raw)
        self._update_headers()

    def _update_headers(self) -> None:
        """Update headers with current cookies."""
        cookie_str = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        self._headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Accept-Language": f"{self._language},{self._language.split('-')[0]};q=0.9",
            "Cookie": cookie_str,
            "Referer": "https://www.reddit.com/",
        }
        # Add CSRF token if available
        if "csrf_token" in self._cookies:
            self._headers["X-CSRF-Token"] = self._cookies["csrf_token"]

    def get_cookies(self) -> dict[str, str]:
        return dict(self._cookies)

    # ── Internal Helpers ───────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> dict:
        """Make authenticated request to Reddit API."""
        full_url = url
        if params:
            full_url = f"{url}?{urlencode(params)}"

        if method == "GET":
            resp = await self._rnet.get(full_url, headers=self._headers)
        elif method == "POST":
            headers = {**self._headers, "Content-Type": "application/json"}
            resp = await self._rnet.post(
                url, headers=headers, json=json_data
            )
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status == 401 or resp.status == 403:
            raise RedditAPIError(resp.status, "Authentication failed")
        if resp.status != 200:
            text = await resp.text()
            raise RedditAPIError(resp.status, text[:500])

        return json.loads(await resp.text())

    # ── Public API ─────────────────────────────────────────────────────

    async def get_user(self, username: str, limit: int = 25) -> dict:
        """Get user profile and recent posts.

        Returns dict with: name, karma, created_utc, posts (list).
        """
        # Get user profile - use www.reddit.com (works with cookies)
        url = f"{API_BASE}/user/{username}/about"
        profile_data = await self._request("GET", url)

        # Get user's submissions - use www.reddit.com
        posts_url = f"{API_BASE}/user/{username}/submitted.json"
        posts_data = await self._request(
            "GET", posts_url, params={"limit": limit}
        )

        user_data = profile_data.get("data", {})
        posts_listing = posts_data.get("data", {}).get("children", [])

        posts = []
        for post in posts_listing:
            post_data = post.get("data", {})
            posts.append({
                "id": post_data.get("id"),
                "title": post_data.get("title"),
                "subreddit": post_data.get("subreddit"),
                "score": post_data.get("score", 0),
                "num_comments": post_data.get("num_comments", 0),
                "created_utc": post_data.get("created_utc", 0),
                "url": post_data.get("url"),
                "permalink": post_data.get("permalink"),
                "is_self": post_data.get("is_self", False),
                "selftext": post_data.get("selftext", "") if post_data.get("is_self") else "",
            })

        return {
            "name": user_data.get("name", username),
            "comment_karma": user_data.get("comment_karma", 0),
            "link_karma": user_data.get("link_karma", 0),
            "total_karma": user_data.get("total_karma", 0),
            "created_utc": user_data.get("created_utc", 0),
            "is_gold": user_data.get("is_gold", False),
            "is_mod": user_data.get("is_mod", False),
            "posts": posts,
            "posts_count": len(posts),
        }

    async def get_subreddit(
        self, name: str, sort: str = "hot", limit: int = 25
    ) -> dict:
        """Get subreddit posts.

        Args:
            name: Subreddit name (without r/)
            sort: 'hot', 'new', 'top', 'rising'
            limit: Number of posts to fetch

        Returns dict with: name, posts (list).
        """
        url = f"{API_BASE}/r/{name}/{sort}.json"
        data = await self._request("GET", url, params={"limit": limit})

        posts = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            posts.append({
                "id": post_data.get("id"),
                "title": post_data.get("title"),
                "author": post_data.get("author"),
                "score": post_data.get("score", 0),
                "num_comments": post_data.get("num_comments", 0),
                "created_utc": post_data.get("created_utc", 0),
                "url": post_data.get("url"),
                "permalink": post_data.get("permalink"),
                "is_self": post_data.get("is_self", False),
                "selftext": post_data.get("selftext", "") if post_data.get("is_self") else "",
                "thumbnail": post_data.get("thumbnail", ""),
            })

        return {
            "name": name,
            "sort": sort,
            "posts": posts,
            "posts_count": len(posts),
        }

    async def get_post(self, post_id: str) -> dict:
        """Get post details with comments.

        Args:
            post_id: Full ID like 't3_abc123' or short 'abc123'

        Returns dict with: post details and comments.
        """
        # Normalize post_id
        if post_id.startswith("t3_"):
            post_id = post_id[3:]

        url = f"{API_BASE}/comments/{post_id}.json"
        data = await self._request("GET", url, params={"limit": 100})

        if not data or len(data) < 1:
            raise RedditAPIError(404, "Post not found")

        # Post data is first listing
        post_listing = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
        # Comments are second listing
        comments_listing = data[1].get("data", {}).get("children", []) if len(data) > 1 else []

        def parse_comment(comment_data: dict) -> dict | None:
            """Recursively parse comment data."""
            if not comment_data or comment_data.get("kind") != "t1":
                return None
            data = comment_data.get("data", {})
            replies = []
            reply_data = data.get("replies")
            if reply_data and isinstance(reply_data, dict):
                for reply in reply_data.get("data", {}).get("children", []):
                    parsed = parse_comment(reply)
                    if parsed:
                        replies.append(parsed)

            return {
                "id": data.get("id"),
                "author": data.get("author"),
                "body": data.get("body", ""),
                "score": data.get("score", 0),
                "created_utc": data.get("created_utc", 0),
                "permalink": data.get("permalink"),
                "replies": replies,
            }

        comments = []
        for comment in comments_listing:
            parsed = parse_comment(comment)
            if parsed:
                comments.append(parsed)

        return {
            "id": post_listing.get("id"),
            "title": post_listing.get("title"),
            "author": post_listing.get("author"),
            "subreddit": post_listing.get("subreddit"),
            "score": post_listing.get("score", 0),
            "num_comments": post_listing.get("num_comments", 0),
            "created_utc": post_listing.get("created_utc", 0),
            "url": post_listing.get("url"),
            "permalink": post_listing.get("permalink"),
            "is_self": post_listing.get("is_self", False),
            "selftext": post_listing.get("selftext", ""),
            "comments": comments,
            "comments_count": len(comments),
        }

    async def search(
        self, query: str, sort: str = "relevance", limit: int = 25
    ) -> list[dict]:
        """Search Reddit posts.

        Args:
            query: Search query
            sort: 'relevance', 'new', 'hot', 'top'
            limit: Number of results

        Returns list of post dicts.
        """
        url = f"{API_BASE}/search.json"
        data = await self._request(
            "GET",
            url,
            params={
                "q": query,
                "sort": sort,
                "type": "link",
                "limit": limit,
            },
        )

        posts = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            posts.append({
                "id": post_data.get("id"),
                "title": post_data.get("title"),
                "author": post_data.get("author"),
                "subreddit": post_data.get("subreddit"),
                "score": post_data.get("score", 0),
                "num_comments": post_data.get("num_comments", 0),
                "created_utc": post_data.get("created_utc", 0),
                "url": post_data.get("url"),
                "permalink": post_data.get("permalink"),
            })

        return posts

    async def upvote(self, post_id: str) -> dict:
        """Upvote a post.

        Args:
            post_id: Full ID like 't3_abc123'
        """
        if not post_id.startswith("t3_"):
            post_id = f"t3_{post_id}"

        url = f"{OAUTH_BASE}/api/vote"
        return await self._request(
            "POST",
            url,
            json_data={"id": post_id, "dir": 1},
        )

    async def downvote(self, post_id: str) -> dict:
        """Downvote a post.

        Args:
            post_id: Full ID like 't3_abc123'
        """
        if not post_id.startswith("t3_"):
            post_id = f"t3_{post_id}"

        url = f"{OAUTH_BASE}/api/vote"
        return await self._request(
            "POST",
            url,
            json_data={"id": post_id, "dir": -1},
        )

    async def comment(self, post_id: str, text: str) -> dict:
        """Comment on a post.

        Args:
            post_id: Full ID like 't3_abc123'
            text: Comment text
        """
        if not post_id.startswith("t3_"):
            post_id = f"t3_{post_id}"

        url = f"{OAUTH_BASE}/api/comment"
        return await self._request(
            "POST",
            url,
            json_data={
                "thing_id": post_id,
                "text": text,
            },
        )

    async def submit(
        self,
        subreddit: str,
        title: str,
        text: str | None = None,
        url: str | None = None,
    ) -> dict:
        """Submit a post to a subreddit.

        Args:
            subreddit: Subreddit name (without r/)
            title: Post title
            text: Selftext (for text posts)
            url: URL (for link posts)

        One of text or url must be provided.
        """
        post_type = "self" if text else "link"

        post_url = f"{OAUTH_BASE}/api/submit"
        json_data = {
            "sr": subreddit,
            "title": title,
            "kind": post_type,
        }
        if text:
            json_data["text"] = text
        if url:
            json_data["url"] = url

        return await self._request("POST", post_url, json_data=json_data)
