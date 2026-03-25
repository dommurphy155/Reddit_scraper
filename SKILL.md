---
name: reddit-scrape
description: Scrape Reddit posts, comments, and user profiles via authenticated API
homepage: https://github.com/dommurphy155/Reddit-scraper
metadata: {"openclaw": {"emoji": "🔴", "os": ["darwin", "linux"], "requires": {"bins": ["python3", "Xvfb"], "env": ["REDDIT_SESSION_PATH"]}}}
---

# Reddit Scraper Skill

Scrape Reddit posts, comments, and user profiles using authenticated cookies.

## ⚠️ Auto-Refresh Limitations

Reddit's bot detection blocks automated logins on cloud VMs. Auto-refresh works on local machines but may fail on servers with:
```
Your request has been blocked by network security.
```

**Workaround**: Use manually extracted cookies (see README.md).

## Quick Start

```bash
# Setup credentials (manual method)
cp reddit_session.json.example reddit_session.json
# Edit with your cookies from Chrome

# Start service
sudo systemctl start reddit-scrape

# Test
reddit status
reddit subreddit python --limit 10
```

## Commands

- `reddit user <username>` - Get user profile + posts
- `reddit subreddit <name>` - Get subreddit posts
- `reddit post <id>` - Get post + comments
- `reddit search "<query>"` - Search posts
- `reddit upvote/downvote <id>` - Vote on posts
- `reddit comment "text" --on <id>` - Add comment
- `reddit submit "title" --to <sub>` - Create post

## Output

JSON files saved to `storage/reddit/`:
- `subreddit_{name}_{sort}.json`
- `user_{username}.json`
- `search_{query}.json`

## Technical

- Uses `rnet` with Chrome TLS emulation
- Port 8766 (HTTP API)
- Requires `reddit_session`, `token_v2`, `csrf_token` cookies
