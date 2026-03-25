#!/usr/bin/env python3
"""Reddit Scraper API Server with AUTO AUTH REFRESH.

This server automatically detects expired sessions (403 errors) and
uses Playwright browser automation to log in and extract fresh cookies.

Endpoints:
    POST /user         - Get user profile + posts
    POST /subreddit    - Get subreddit posts
    POST /post         - Get post + comments
    POST /search       - Search posts
    POST /upvote       - Upvote a post
    POST /downvote     - Downvote a post
    POST /comment      - Comment on a post
    POST /submit       - Create a post
    GET  /health       - Health check
    POST /refresh      - Manually trigger auth refresh

Auto-refresh: Enabled - server will automatically re-login on auth failures.
"""

import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from reddit_client import RedditClient, RedditAPIError
from auth_refresh import refresh_auth, AuthRefreshError, SESSION_PATH

# Config
HOST = os.environ.get("REDDIT_SCRAPE_HOST", "127.0.0.1")
PORT = int(os.environ.get("REDDIT_SCRAPE_PORT", "8766"))
STORAGE_DIR = Path("storage/reddit")

# Ensure storage dir exists
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Global to track if we're currently refreshing
auth_being_refreshed = False

# Cookie refresh scheduler
COOKIE_REFRESH_INTERVAL_HOURS = 6
last_cookie_refresh = None


async def keep_session_alive():
    """Background task to keep cookies fresh by making periodic requests.

    Reddit refreshes session expiration server-side when cookies are used.
    We just need to make any authenticated request every ~23 hours.
    """
    global last_cookie_refresh

    while True:
        try:
            # Wait first, then check
            await asyncio.sleep(COOKIE_REFRESH_INTERVAL_HOURS * 3600)

            if not SESSION_PATH.exists():
                print("[KeepAlive] No session file, skipping refresh")
                continue

            print(f"[KeepAlive] Making periodic request to refresh cookies...")

            client = RedditClient()
            client.load_cookies(str(SESSION_PATH))

            # Make a simple request - this refreshes the session server-side
            # Getting the front page is lightweight and keeps session alive
            await client.get_subreddit("announcements", limit=1)

            last_cookie_refresh = datetime.now()
            print(f"[KeepAlive] Session refreshed at {last_cookie_refresh.isoformat()}")

        except Exception as e:
            print(f"[KeepAlive] Error refreshing session: {e}")
            # Don't retry immediately, wait for next interval


def start_keep_alive_task():
    """Start the background keep-alive task."""
    asyncio.create_task(keep_session_alive())
    print(f"[KeepAlive] Scheduled cookie refresh every {COOKIE_REFRESH_INTERVAL_HOURS} hours")

# Cookie refresh schedule (23 hours in seconds)
COOKIE_REFRESH_INTERVAL = 23 * 60 * 60  # 23 hours
last_cookie_refresh = None


def response(status_code, data):
    """Build JSON response."""
    return status_code, {"Content-Type": "application/json"}, json.dumps(data).encode()


async def ensure_valid_auth():
    """
    Check if auth is valid, refresh if needed.

    Returns True if valid auth exists, False otherwise.
    """
    global auth_being_refreshed

    # Test current session
    if SESSION_PATH.exists():
        client = RedditClient()
        try:
            client.load_cookies(str(SESSION_PATH))
            # Try a simple API call
            await client.get_subreddit("announcements", limit=1)
            print("[Server] Session is valid")
            return True
        except RedditAPIError as e:
            if e.status in [401, 403]:
                print(f"[Server] Session expired (HTTP {e.status}), auto-refreshing...")
            else:
                print(f"[Server] Session test error (non-auth): {e}")
                return True
        except Exception as e:
            print(f"[Server] Session test error: {e}")

    # Need to refresh
    if auth_being_refreshed:
        print("[Server] Auth refresh already in progress, waiting...")
        for _ in range(60):
            await asyncio.sleep(1)
            if not auth_being_refreshed:
                break
        return SESSION_PATH.exists()

    auth_being_refreshed = True
    try:
        print("[Server] Starting automatic auth refresh...")
        await refresh_auth(headless=True)
        print("[Server] Auth refresh successful!")
        return True
    except AuthRefreshError as e:
        print(f"[Server] Auth refresh failed: {e}")
        return False
    finally:
        auth_being_refreshed = False


class RedditHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Reddit API."""

    def log_message(self, format, *args):
        """Custom logging."""
        print(f"[{datetime.now().isoformat()}] {args[0]}")

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            session_exists = SESSION_PATH.exists()
            session_valid = False
            if session_exists:
                try:
                    session_valid = asyncio.run(self._test_session_quick())
                except:
                    pass
            self._send(*response(200, {
                "status": "ok",
                "session_exists": session_exists,
                "session_valid": session_valid,
                "endpoint": f"{HOST}:{PORT}"
            }))
        else:
            self._send(*response(404, {"error": "Not found"}))

    async def _test_session_quick(self):
        """Quick test if session works."""
        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))
        await client.get_subreddit("announcements", limit=1)
        return True

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send(*response(400, {"error": "Invalid JSON"}))
            return

        handlers = {
            "/user": self._handle_user,
            "/subreddit": self._handle_subreddit,
            "/post": self._handle_post,
            "/search": self._handle_search,
            "/upvote": self._handle_upvote,
            "/downvote": self._handle_downvote,
            "/comment": self._handle_comment,
            "/submit": self._handle_submit,
            "/refresh": self._handle_refresh,
        }

        handler = handlers.get(self.path)
        if handler:
            handler(data)
        else:
            self._send(*response(404, {"error": "Unknown endpoint"}))

    def _send(self, status, headers, body):
        """Send HTTP response."""
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _handle_with_retry(self, handler_func, data, operation_name="Operation"):
        """Execute handler with automatic auth refresh on failure."""
        if not asyncio.run(ensure_valid_auth()):
            self._send(*response(401, {
                "error": "Authentication failed. Check .reddit_config.json"
            }))
            return

        try:
            result = asyncio.run(handler_func(data))
            result["_meta"] = {"refreshed": False, "message": f"{operation_name} successful"}
            self._send(*response(200, result))
        except RedditAPIError as e:
            if e.status in [401, 403]:
                print(f"[Server] Auth error {e.status}, attempting refresh and retry...")
                if asyncio.run(ensure_valid_auth()):
                    try:
                        result = asyncio.run(handler_func(data))
                        result["_meta"] = {"refreshed": True, "message": f"Session expired, refreshed, then {operation_name.lower()} successful"}
                        self._send(*response(200, result))
                        return
                    except RedditAPIError as e2:
                        self._send(*response(e2.status, {"error": str(e2)}))
                        return
                else:
                    self._send(*response(401, {"error": "Auth failed and refresh failed"}))
            else:
                self._send(*response(e.status, {"error": str(e)}))
        except Exception as e:
            self._send(*response(500, {"error": str(e)}))

    def _handle_user(self, data):
        """Get user profile and posts."""
        self._handle_with_retry(self._do_user, data, "User fetch")

    async def _do_user(self, data):
        """Actually get user."""
        username = data.get("username")
        limit = data.get("limit", 25)

        if not username:
            raise ValueError("username required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))

        user_data = await client.get_user(username, limit=limit)

        output = {
            "scraped_at": datetime.now().isoformat(),
            "username": username,
            **user_data,
        }

        output_path = STORAGE_DIR / f"user_{username}.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        return {"success": True, "path": str(output_path), "posts_count": user_data["posts_count"]}

    def _handle_subreddit(self, data):
        """Get subreddit posts."""
        self._handle_with_retry(self._do_subreddit, data, "Subreddit fetch")

    async def _do_subreddit(self, data):
        """Actually get subreddit."""
        name = data.get("name")
        sort = data.get("sort", "hot")
        limit = data.get("limit", 25)

        if not name:
            raise ValueError("name required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))

        sub_data = await client.get_subreddit(name, sort=sort, limit=limit)

        output = {
            "scraped_at": datetime.now().isoformat(),
            **sub_data,
        }

        output_path = STORAGE_DIR / f"subreddit_{name}_{sort}.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        return {"success": True, "path": str(output_path), "posts_count": sub_data["posts_count"]}

    def _handle_post(self, data):
        """Get post with comments."""
        self._handle_with_retry(self._do_post, data, "Post fetch")

    async def _do_post(self, data):
        """Actually get post."""
        post_id = data.get("post_id")

        if not post_id:
            raise ValueError("post_id required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))

        post_data = await client.get_post(post_id)

        output = {
            "scraped_at": datetime.now().isoformat(),
            **post_data,
        }

        output_path = STORAGE_DIR / f"post_{post_id}.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        return {"success": True, "path": str(output_path), "comments_count": post_data["comments_count"]}

    def _handle_search(self, data):
        """Search posts."""
        self._handle_with_retry(self._do_search, data, "Search")

    async def _do_search(self, data):
        """Actually search."""
        query = data.get("query")
        sort = data.get("sort", "relevance")
        limit = data.get("limit", 25)

        if not query:
            raise ValueError("query required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))

        posts = await client.search(query, sort=sort, limit=limit)

        output = {
            "scraped_at": datetime.now().isoformat(),
            "query": query,
            "sort": sort,
            "posts": posts,
            "posts_count": len(posts),
        }

        safe_query = query.replace(" ", "_").replace(":", "")[:50]
        output_path = STORAGE_DIR / f"search_{safe_query}.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        return {"success": True, "path": str(output_path), "posts_count": len(posts), "posts": posts}

    def _handle_upvote(self, data):
        """Upvote a post."""
        self._handle_with_retry(self._do_upvote, data, "Upvote")

    async def _do_upvote(self, data):
        """Actually upvote."""
        post_id = data.get("post_id")
        if not post_id:
            raise ValueError("post_id required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))
        await client.upvote(post_id)
        return {"success": True}

    def _handle_downvote(self, data):
        """Downvote a post."""
        self._handle_with_retry(self._do_downvote, data, "Downvote")

    async def _do_downvote(self, data):
        """Actually downvote."""
        post_id = data.get("post_id")
        if not post_id:
            raise ValueError("post_id required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))
        await client.downvote(post_id)
        return {"success": True}

    def _handle_comment(self, data):
        """Comment on a post."""
        self._handle_with_retry(self._do_comment, data, "Comment")

    async def _do_comment(self, data):
        """Actually comment."""
        post_id = data.get("post_id")
        text = data.get("text")

        if not post_id or not text:
            raise ValueError("post_id and text required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))
        result = await client.comment(post_id, text)
        return {"success": True, "comment_id": result.get("json", {}).get("data", {}).get("things", [{}])[0].get("data", {}).get("id")}

    def _handle_submit(self, data):
        """Submit a post."""
        self._handle_with_retry(self._do_submit, data, "Submit")

    async def _do_submit(self, data):
        """Actually submit."""
        subreddit = data.get("subreddit")
        title = data.get("title")
        body = data.get("body")
        url = data.get("url")

        if not subreddit or not title:
            raise ValueError("subreddit and title required")

        client = RedditClient()
        client.load_cookies(str(SESSION_PATH))
        result = await client.submit(subreddit, title, text=body, url=url)
        post_id = result.get("json", {}).get("data", {}).get("id")
        return {"success": True, "post_id": post_id, "url": f"https://reddit.com/r/{subreddit}/comments/{post_id}"}

    def _handle_refresh(self, data):
        """Manually trigger auth refresh."""
        try:
            success = asyncio.run(ensure_valid_auth())
            if success:
                self._send(*response(200, {"success": True, "message": "Session refreshed"}))
            else:
                self._send(*response(500, {"error": "Refresh failed"}))
        except Exception as e:
            self._send(*response(500, {"error": str(e)}))


def run_keep_alive_in_thread():
    """Run the keep-alive asyncio task in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(keep_session_alive())


def run_server():
    """Run the HTTP server."""
    server = HTTPServer((HOST, PORT), RedditHandler)
    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║     Reddit Scraper Server - AUTO AUTH REFRESH            ║")
    print(f"╠═══════════════════════════════════════════════════════════╣")
    print(f"║  Endpoint: http://{HOST}:{PORT}                      ║")
    print(f"║  Storage:  {STORAGE_DIR}        ║")
    print(f"║  Session: {SESSION_PATH}                ║")
    print(f"║                                                           ║")
    print(f"║  Features:                                                ║")
    print(f"║  • Automatic session refresh on 403/401 errors            ║")
    print(f"║  • Cookie keep-alive every 23 hours                       ║")
    print(f"║  • Playwright browser automation for re-login          ║")
    print(f"║  • Headless Chrome - no GUI required                     ║")
    print(f"║                                                           ║")
    print(f"║  Setup:                                                   ║")
    print(f"║  1. cp .reddit_config.example.json .reddit_config.json   ║")
    print(f"║  2. Edit with your Reddit credentials                   ║")
    print(f"║                                                           ║")
    print(f"╚═══════════════════════════════════════════════════════════╝")
    print()

    config_path = Path(__file__).parent / ".reddit_config.json"
    if not config_path.exists():
        print("⚠️  WARNING: .reddit_config.json not found!")
        print("   Auto-refresh will fail until you create it.")
        print("   Copy .reddit_config.example.json and fill in your credentials.\n")

    # Start the keep-alive thread
    if SESSION_PATH.exists():
        print(f"[KeepAlive] Starting background cookie refresh thread...")
        print(f"[KeepAlive] Will refresh cookies every {COOKIE_REFRESH_INTERVAL_HOURS} hours")
        keep_alive_thread = threading.Thread(target=run_keep_alive_in_thread, daemon=True)
        keep_alive_thread.start()
    else:
        print("[KeepAlive] No existing session, skipping background refresh")
        print("            (cookies will be refreshed after first manual setup)\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
