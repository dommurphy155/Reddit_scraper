#!/usr/bin/env python3
"""Extract Reddit cookies from Chrome/Chromium.

This script helps extract cookies from an existing browser session.
It requires you to be logged into Reddit in Chrome.

Usage:
    python get_cookies.py        # Extract from Chrome
    python get_cookies.py firefox # Extract from Firefox
"""

import json
import os
import sys
import sqlite3
import tempfile
import shutil
from pathlib import Path


def get_chrome_cookies():
    """Extract Reddit cookies from Chrome/Chromium."""
    cookie_paths = [
        # Linux
        Path.home() / ".config/google-chrome/Default/Cookies",
        Path.home() / ".config/chromium/Default/Cookies",
        Path.home() / ".var/app/com.google.Chrome/config/google-chrome/Default/Cookies",
        # macOS
        Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies",
        Path.home() / "Library/Application Support/Chromium/Default/Cookies",
    ]

    for cookie_path in cookie_paths:
        if cookie_path.exists():
            return extract_sqlite_cookies(cookie_path, "reddit.com")

    return None


def get_firefox_cookies():
    """Extract Reddit cookies from Firefox."""
    profile_paths = [
        Path.home() / ".mozilla/firefox",
        Path.home() / "Library/Application Support/Firefox/Profiles",
    ]

    for base_path in profile_paths:
        if base_path.exists():
            for profile in base_path.iterdir():
                if profile.is_dir() and ".default" in profile.name:
                    cookie_path = profile / "cookies.sqlite"
                    if cookie_path.exists():
                        return extract_sqlite_cookies(cookie_path, "reddit.com")

    return None


def extract_sqlite_cookies(db_path: Path, domain: str):
    """Extract cookies from SQLite database."""
    # Copy to temp location (Chrome locks the file)
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    shutil.copy2(db_path, temp_db.name)
    temp_db.close()

    try:
        conn = sqlite3.connect(temp_db.name)
        cursor = conn.cursor()

        # Chrome format
        try:
            cursor.execute(
                "SELECT name, value, host_key FROM cookies WHERE host_key LIKE ?",
                (f"%{domain}%",)
            )
            cookies = cursor.fetchall()
            if cookies:
                return [
                    {"name": name, "value": value}
                    for name, value, host in cookies
                    if name in ["reddit_session", "token_v2", "csrf_token"]
                ]
        except sqlite3.OperationalError:
            pass

        # Firefox format
        try:
            cursor.execute(
                "SELECT name, value, host FROM moz_cookies WHERE host LIKE ?",
                (f"%{domain}%",)
            )
            cookies = cursor.fetchall()
            if cookies:
                return [
                    {"name": name, "value": value}
                    for name, value, host in cookies
                    if name in ["reddit_session", "token_v2", "csrf_token"]
                ]
        except sqlite3.OperationalError:
            pass

        return None
    finally:
        os.unlink(temp_db.name)


def manual_instructions():
    """Print manual cookie extraction instructions."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║  Manual Reddit Cookie Extraction                                ║
╠════════════════════════════════════════════════════════════════╣
║  1. Open Chrome and log into Reddit                            ║
║  2. Press F12 to open DevTools                                   ║
║  3. Go to Application → Cookies → https://www.reddit.com       ║
║  4. Copy these cookies:                                          ║
║                                                                 ║
║     • reddit_session   (long JWT token)                         ║
║     • token_v2         (long JWT token)                         ║
║     • csrf_token       (short hex string)                     ║
║                                                                 ║
║  5. Create file: ~/.openclaw/skills/reddit_scrape/            ║
║     reddit_session.json                                          ║
║                                                                 ║
║  Format:                                                         ║
║  [                                                               ║
║    {"name": "reddit_session", "value": "eyJ..."},              ║
║    {"name": "token_v2", "value": "eyJ..."},                    ║
║    {"name": "csrf_token", "value": "abc123..."}                ║
║  ]                                                               ║
║                                                                 ║
║  6. Test: reddit status                                         ║
╚════════════════════════════════════════════════════════════════╝
""")


def main():
    browser = sys.argv[1] if len(sys.argv) > 1 else "chrome"

    print(f"Attempting to extract cookies from {browser}...")

    if browser == "chrome":
        cookies = get_chrome_cookies()
    elif browser == "firefox":
        cookies = get_firefox_cookies()
    else:
        print(f"Unknown browser: {browser}")
        print("Usage: python get_cookies.py [chrome|firefox]")
        sys.exit(1)

    if cookies:
        # Check if we have the essential cookies
        names = {c["name"] for c in cookies}
        if "reddit_session" in names:
            output_path = Path(__file__).parent / "reddit_session.json"
            output_path.write_text(json.dumps(cookies, indent=2))
            print(f"✓ Successfully extracted {len(cookies)} cookies")
            print(f"✓ Saved to: {output_path}")
            print(f"  Cookies: {', '.join(names)}")
            return

    print("\n✗ Could not extract cookies automatically.")
    print("   Chrome may be running or cookies are encrypted.")
    print()
    manual_instructions()


if __name__ == "__main__":
    main()
