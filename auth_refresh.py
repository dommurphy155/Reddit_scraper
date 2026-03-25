#!/usr/bin/env python3
"""Automatic authentication refresh for Reddit using Playwright with stealth.

Uses playwright-stealth to evade bot detection and simulates human-like behavior.
"""

import asyncio
import json
import os
import sys
import random
from pathlib import Path
from typing import Optional

# Config file for credentials (NOT in git)
CONFIG_PATH = Path(__file__).parent / ".reddit_config.json"
SESSION_PATH = Path(__file__).parent / "reddit_session.json"


class AuthRefreshError(Exception):
    """Raised when auth refresh fails."""
    pass


def load_credentials() -> tuple[str, str]:
    """Load Reddit credentials from config file."""
    if not CONFIG_PATH.exists():
        raise AuthRefreshError(
            f"Credentials file not found: {CONFIG_PATH}\n"
            "Create it with:\n"
            '{"username": "your_handle", "password": "your_pass"}'
        )

    config = json.loads(CONFIG_PATH.read_text())
    username = config.get("username")
    password = config.get("password")

    if not username or not password:
        raise AuthRefreshError("Config must contain 'username' and 'password'")

    return username, password


async def human_like_typing(page, selector: str, text: str):
    """Type text like a human with random delays between keystrokes."""
    await page.focus(selector)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(50, 150))
        await asyncio.sleep(random.uniform(0.01, 0.05))


async def human_like_delay(min_seconds: float = 0.5, max_seconds: float = 2.0):
    """Wait for a random amount of time like a human would."""
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


async def refresh_auth(
    headless: bool = True,
    timeout: int = 120
) -> list[dict]:
    """Refresh Reddit session using stealth browser automation.

    Args:
        headless: Run browser in headless mode
        timeout: Maximum time to wait for login (seconds)

    Returns:
        List of cookie dicts with 'name' and 'value' keys
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
        from playwright_stealth import Stealth
        from xvfbwrapper import Xvfb
    except ImportError as e:
        raise AuthRefreshError(f"Missing dependency: {e}. Run: pip install playwright-stealth xvfbwrapper")

    username, password = load_credentials()

    print(f"[AuthRefresh] Starting stealth browser for u/{username}...")

    # Set up virtual display for headless servers
    display = None
    if headless and not os.environ.get('DISPLAY'):
        print("[AuthRefresh] Setting up virtual display...")
        display = Xvfb(width=1920, height=1080, colordepth=24)
        display.start()
        launch_headless = False  # We have a display now
    else:
        launch_headless = headless

    async with async_playwright() as p:
        # Launch with stealth args
        browser = await p.chromium.launch(
            headless=launch_headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--disable-blink-features=AutomationControlled',
            ]
        )

        # Create context with realistic viewport and locale
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            geolocation={'latitude': 40.7128, 'longitude': -74.0060},  # NYC
            permissions=['geolocation'],
            color_scheme='light',
        )

        # Add stealth scripts to evade detection
        page = await context.new_page()
        stealth_config = Stealth()
        await stealth_config.apply_stealth_async(page)

        try:
            # Go directly to login page
            print("[AuthRefresh] Navigating to login page...")
            await page.goto('https://www.reddit.com/login', wait_until='networkidle', timeout=timeout*1000)
            await human_like_delay(2, 4)

            # Wait for login form - modern Reddit uses input with autocomplete
            print("[AuthRefresh] Waiting for login form...")
            await page.wait_for_selector('input[name="username"], input[autocomplete="username"]', timeout=timeout*1000)
            await human_like_delay(1, 2)

            # Fill username
            print("[AuthRefresh] Entering username...")
            await human_like_typing(page, 'input[name="username"], input[autocomplete="username"]', username)
            await human_like_delay(0.5, 1.5)

            # Fill password
            print("[AuthRefresh] Entering password...")
            await human_like_typing(page, 'input[name="password"], input[type="password"]', password)
            await human_like_delay(0.5, 1.0)

            # Submit form
            print("[AuthRefresh] Submitting login...")
            submit_btn = await page.wait_for_selector('button[type="submit"]', timeout=5000)
            if submit_btn:
                await human_like_delay(0.3, 0.7)
                await submit_btn.click()

            # Wait for login to complete
            print("[AuthRefresh] Waiting for login to complete...")
            await asyncio.sleep(3)

            # Check for errors
            error_elem = await page.query_selector('.error, .flash-error')
            if error_elem:
                error_text = await error_elem.text_content()
                if error_text and error_text.strip():
                    raise AuthRefreshError(f"Login failed: {error_text.strip()}")

            # Navigate to get cookies from www.reddit.com
            print("[AuthRefresh] Navigating to get session cookies...")
            await page.goto('https://www.reddit.com', wait_until='networkidle')
            await asyncio.sleep(3)

            # Extract cookies
            cookies = await context.cookies()

            # Filter to auth cookies
            auth_cookies = [
                {"name": c["name"], "value": c["value"]}
                for c in cookies
                if c["name"] in ["reddit_session", "token_v2", "csrf_token", "session_tracker"]
            ]

            # Ensure we have reddit_session
            cookie_names = {c["name"] for c in auth_cookies}
            if "reddit_session" not in cookie_names:
                # Take screenshot for debugging
                screenshot_path = Path(__file__).parent / "login_error.png"
                await page.screenshot(path=str(screenshot_path))
                raise AuthRefreshError(f"reddit_session not found. Screenshot: {screenshot_path}")

            print(f"[AuthRefresh] Successfully extracted {len(auth_cookies)} cookies")

            # Save to file
            SESSION_PATH.write_text(json.dumps(auth_cookies, indent=2))
            print(f"[AuthRefresh] Session saved to {SESSION_PATH}")

            return auth_cookies

        except PlaywrightTimeout as e:
            screenshot_path = Path(__file__).parent / "login_error.png"
            await page.screenshot(path=str(screenshot_path))
            raise AuthRefreshError(f"Timeout: {e}. Screenshot: {screenshot_path}")

        except Exception as e:
            raise AuthRefreshError(f"Login failed: {e}")

        finally:
            await browser.close()
            if display:
                display.stop()
                print("[AuthRefresh] Virtual display stopped")


def refresh_auth_sync(headless: bool = True) -> list[dict]:
    """Synchronous wrapper for refresh_auth."""
    return asyncio.run(refresh_auth(headless=headless))


def needs_refresh() -> bool:
    """Check if session needs refresh."""
    if not SESSION_PATH.exists():
        return True

    try:
        cookies = json.loads(SESSION_PATH.read_text())
        if not cookies:
            return True
        cookie_names = {c.get("name") for c in cookies}
        return "reddit_session" not in cookie_names
    except:
        return True


async def test_session(cookies_path: str = None) -> bool:
    """Test if current session is valid."""
    from reddit_client import RedditClient, RedditAPIError

    path = cookies_path or str(SESSION_PATH)
    if not Path(path).exists():
        return False

    client = RedditClient()
    try:
        client.load_cookies(path)
        await client.get_subreddit("announcements", limit=1)
        return True
    except RedditAPIError as e:
        if e.status in [403, 401]:
            return False
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Refresh Reddit session")
    parser.add_argument("--visible", "-v", action="store_true", help="Show browser window")
    parser.add_argument("--test", "-t", action="store_true", help="Test current session")
    args = parser.parse_args()

    if args.test:
        print("Testing current session...")
        valid = asyncio.run(test_session())
        print(f"Session valid: {valid}")
        sys.exit(0 if valid else 1)

    try:
        cookies = asyncio.run(refresh_auth(headless=not args.visible))
        print(f"\n✓ Success! Got {len(cookies)} cookies")
        for c in cookies:
            masked = c['value'][:20] + "..." if len(c['value']) > 20 else c['value']
            print(f"  - {c['name']}: {masked}")
    except AuthRefreshError as e:
        print(f"\n✗ Failed: {e}", file=sys.stderr)
        sys.exit(1)
