# Reddit Scraper CLI (`reddit`)

A systemd-powered Reddit scraper with automatic session refresh that runs as a background service with a simple `reddit` command available everywhere on your system.

## ⚠️ Important Note on Session Refresh

**Cookie Keep-Alive**: The server automatically keeps your session alive by making a request every 23 hours. This refreshes the cookies server-side without needing to re-login.

**Initial Setup**: You need to manually extract cookies once (see below). After that, the keep-alive maintains them indefinitely as long as the server runs.

**If Session Expires**: If cookies do expire (e.g., server was down), you'll need to manually extract fresh cookies from Chrome.

## ✨ Key Features

- **Cookie-based Auth**: Uses `reddit_session`, `token_v2`, `csrf_token` cookies
- **Auto Keep-Alive**: Server pings Reddit every 23 hours to keep session fresh
- **Global CLI**: `reddit` command works from any directory
- **Cloudflare Bypass**: Uses Chrome TLS fingerprint emulation via `rnet`
- **Xvfb Support**: Virtual display for headless browser automation (when it works)

## 🏗️ Architecture

Same client-server model as the Twitter scraper:
- Server runs on port 8766
- CLI talks via HTTP (stdlib only)
- Systemd service for background operation

## 🚀 Installation

```bash
# 1. Already installed at ~/.openclaw/skills/reddit_scrape/
cd ~/.openclaw/skills/reddit_scrape

# 2. Install service (uses Twitter's venv)
sudo bash install-service.sh

# 3. Set up credentials (see "Getting Cookies Manually")
nano reddit_session.json  # Paste your cookies

# 4. Start service
sudo systemctl start reddit-scrape

# 5. Test
reddit status
```

## 🔑 Getting Cookies Manually

Since auto-refresh may be blocked:

1. **Open Chrome** → Log into Reddit
2. **DevTools (F12)** → Application → Storage → Cookies → `https://www.reddit.com`
3. **Find and copy these cookies** (double-click value, copy):
   - `reddit_session` (long JWT starting with eyJ...)
   - `token_v2` (long JWT starting with eyJ...)
   - `csrf_token` (short hex string like 76d873...)
4. **Create file** `~/.openclaw/skills/reddit_scrape/reddit_session.json`:
```json
[
  {"name": "reddit_session", "value": "eyJhbG..."},
  {"name": "token_v2", "value": "eyJhbG..."},
  {"name": "csrf_token", "value": "76d8730d..."}
]
```

5. **Restart service**:
```bash
sudo systemctl restart reddit-scrape
reddit status  # Should show session valid
```

**Note**: Chrome 80+ encrypts cookies - the extraction script may get empty values. Use DevTools method above.

## 📋 Commands

```bash
reddit status                           # Check server + session status
reddit user <username> [--limit 25]     # Get user profile + posts
reddit subreddit <name> [--sort hot]    # Get subreddit posts
reddit post <post_id>                   # Get post + comments
reddit search "<query>" [--sort new]    # Search posts
reddit upvote <post_id>                 # Upvote a post
reddit downvote <post_id>               # Downvote a post
reddit comment "<text>" --on <post_id>  # Comment on a post
reddit submit "<title>" --to <sub>      # Create a post
reddit refresh                          # Force session refresh (may fail on cloud)
```

## 🔧 Service Management

```bash
sudo systemctl status reddit-scrape
sudo systemctl restart reddit-scrape
sudo journalctl -u reddit-scrape -f
```

## 📁 File Locations

| File | Purpose |
|------|---------|
| `server.py` | API server (port 8766) |
| `reddit` | CLI client |
| `reddit_client.py` | Reddit API client |
| `auth_refresh.py` | Browser automation (limited on cloud) |
| `reddit_session.json` | Your auth cookies |
| `storage/reddit/` | Scraped JSON outputs |

## 🛡️ Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "blocked by network security" | Reddit bot detection | Use manual cookies (see above) |
| "Session invalid" | Cookies expired | Get fresh cookies from browser |
| "Cannot connect to server" | Service not running | `sudo systemctl start reddit-scrape` |

## 📝 Technical Notes

- Uses `rnet` with `Emulation.Chrome133` for TLS fingerprint spoofing
- Read operations use `www.reddit.com/*.json` (works with cookies)
- Write operations need OAuth (requires token_v2)
- Xvfb (virtual display) included for headless browser when auto-refresh works
