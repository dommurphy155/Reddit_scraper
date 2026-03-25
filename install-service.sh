#!/bin/bash
# Install systemd service for reddit-scrape with auto-auth-refresh

set -e

echo "Installing Reddit Scrape systemd service..."
echo ""

# Check if running as root (we need sudo for systemctl)
if [ "$EUID" -ne 0 ]; then
    echo "This script needs sudo privileges."
    echo "Run: sudo bash install-service.sh"
    exit 1
fi

# Get the user who ran sudo (not root)
SUDO_USER=${SUDO_USER:-$USER}
SKILL_DIR="/home/${SUDO_USER}/.openclaw/skills/reddit_scrape"

echo "Installing for user: ${SUDO_USER}"
echo "Skill directory: ${SKILL_DIR}"
echo ""

# Check skill directory exists
if [ ! -d "$SKILL_DIR" ]; then
    echo "Error: Skill directory not found at ${SKILL_DIR}"
    exit 1
fi

cd "$SKILL_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3.12 -m venv venv || python3 -m venv venv
fi

# Install dependencies
echo "Installing dependencies..."
./venv/bin/pip install rnet --pre
./venv/bin/pip install playwright

# Install Chromium browser
echo "Installing Chromium browser for Playwright..."
./venv/bin/playwright install chromium

echo ""
echo "Setting up systemd service..."

# Copy service file
cat > /etc/systemd/system/reddit-scrape.service << EOF
[Unit]
Description=Reddit Scraper API Server with Auto Auth Refresh
After=network.target

[Service]
Type=simple
User=${SUDO_USER}
WorkingDirectory=${SKILL_DIR}
Environment="REDDIT_SESSION_PATH=${SKILL_DIR}/reddit_session.json"
Environment="REDDIT_SCRAPE_HOST=127.0.0.1"
Environment="REDDIT_SCRAPE_PORT=8766"
Environment="PLAYWRIGHT_BROWSERS_PATH=0"
ExecStart=${SKILL_DIR}/venv/bin/python ${SKILL_DIR}/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable service (but don't start yet - need config)
systemctl enable reddit-scrape

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              Installation Complete!                        ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Service:     sudo systemctl status reddit-scrape          ║"
echo "║  Logs:        sudo journalctl -u reddit-scrape -f          ║"
echo "║                                                            ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  IMPORTANT: Set up auto-refresh credentials:               ║"
echo "║                                                            ║"
echo "║  1. cp .reddit_config.example.json .reddit_config.json     ║"
echo "║  2. Edit .reddit_config.json with your credentials         ║"
echo "║  3. sudo systemctl start reddit-scrape                     ║"
echo "║  4. Test: reddit status                                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
