#!/usr/bin/env python3
"""
Reddit Scrape Setup Wizard
Installs and configures the reddit_scrape skill with systemd service.
"""

import os
import sys
import json
import subprocess
import time
import shutil
from pathlib import Path
from typing import List, Tuple


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_colored(text: str, color: str = ""):
    """Print colored text."""
    if color:
        print(f"{color}{text}{Colors.END}")
    else:
        print(text)


def print_step(step_num: int, total: int, description: str):
    """Print a step header."""
    print()
    print_colored(f"{'='*60}", Colors.CYAN)
    print_colored(f"  STEP {step_num}/{total}: {description}", Colors.BOLD + Colors.CYAN)
    print_colored(f"{'='*60}", Colors.CYAN)
    print()


def run_command(cmd: List[str], capture: bool = True, check: bool = True, sudo: bool = False, cwd: str = None) -> Tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    if sudo and os.geteuid() != 0:
        cmd = ['sudo'] + cmd

    try:
        if capture:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                cwd=cwd
            )
            return result.returncode, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, check=check, cwd=cwd)
            return result.returncode, "", ""
    except Exception as e:
        return 1, "", str(e)


def prompt_user(message: str, default: str = "") -> str:
    """Prompt user for input with optional default value."""
    if default:
        response = input(f"{message} [{default}]: ").strip()
        return response if response else default
    return input(f"{message}: ").strip()


def confirm(message: str) -> bool:
    """Ask for yes/no confirmation."""
    while True:
        response = input(f"{message} (yes/no): ").strip().lower()
        if response in ('y', 'yes'):
            return True
        if response in ('n', 'no'):
            return False
        print("Please answer 'yes' or 'no'.")


def check_python_version() -> bool:
    """Check if Python 3.10+ is installed."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print_colored(f"Python {version.major}.{version.minor} found. Python 3.10+ required.", Colors.FAIL)
        return False
    print_colored(f"Python {version.major}.{version.minor}.{version.micro} - OK", Colors.GREEN)
    return True


def get_skill_dir() -> Path:
    """Get the skill directory."""
    return Path.home() / ".openclaw" / "skills" / "reddit_scrape"


def get_venv_path() -> Path:
    """Get or create Python virtual environment."""
    skill_dir = get_skill_dir()
    venv_path = skill_dir / "venv"

    # Check if venv exists (could be a symlink)
    if venv_path.exists() or venv_path.is_symlink():
        return venv_path

    # Check if twitter_scrape venv exists (can be reused)
    twitter_venv = Path.home() / ".openclaw" / "skills" / "twitter_scrape" / "venv"
    if twitter_venv.exists():
        print("Linking to existing Twitter scrape virtual environment...")
        venv_path.symlink_to(twitter_venv)
        return venv_path

    print("Creating Python virtual environment...")
    run_command([sys.executable, "-m", "venv", str(venv_path)], check=True)
    return venv_path


def get_venv_python() -> Path:
    """Get the Python executable path in the virtual environment."""
    venv = get_venv_path()
    return venv / "bin" / "python"


def get_venv_pip() -> Path:
    """Get the pip executable path in the virtual environment."""
    venv = get_venv_path()
    return venv / "bin" / "pip"


def check_and_install_dependencies() -> bool:
    """Check and install required Python packages."""
    pip = get_venv_pip()
    python = get_venv_python()

    # Ensure venv exists
    get_venv_path()

    required_packages = ['rnet', 'playwright', 'playwright-stealth', 'xvfbwrapper']

    print("Checking dependencies...")
    for package in required_packages:
        print(f"  Installing {package}...")
        code, out, err = run_command([str(pip), 'install', package, '--pre'] if package == 'rnet' else [str(pip), 'install', package])
        if code != 0:
            print_colored(f"  Failed to install {package}: {err}", Colors.WARNING)

    # Install Playwright browsers
    print("  Installing Playwright Chromium browser...")
    code, out, err = run_command([str(python), '-m', 'playwright', 'install', 'chromium'])
    if code != 0:
        print_colored(f"  Failed to install Chromium: {err}", Colors.WARNING)
        return False

    print_colored("Dependencies installed successfully.", Colors.GREEN)
    return True


def setup_credentials() -> bool:
    """Set up Reddit credentials."""
    skill_dir = get_skill_dir()
    config_path = skill_dir / ".reddit_config.json"

    print_colored("Reddit credentials are required for automatic session refresh.", Colors.CYAN)
    print("These will be stored in .reddit_config.json (not committed to git).")
    print()

    if config_path.exists():
        print_colored("Existing credentials found.", Colors.GREEN)
        try:
            with open(config_path) as f:
                config = json.load(f)
            print(f"  Username: {config.get('username', 'N/A')}")
            if confirm("Use existing credentials?"):
                return True
        except:
            pass

    print()
    print("Enter your Reddit credentials:")
    username = prompt_user("Reddit username")
    password = prompt_user("Reddit password")

    if not username or not password:
        print_colored("Username and password are required.", Colors.FAIL)
        return False

    config = {
        "username": username,
        "password": password
    }

    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        # Set restrictive permissions
        os.chmod(config_path, 0o600)
        print_colored(f"Credentials saved to {config_path}", Colors.GREEN)
        return True
    except Exception as e:
        print_colored(f"Failed to save credentials: {e}", Colors.FAIL)
        return False


def setup_session() -> bool:
    """Set up Reddit session cookies."""
    skill_dir = get_skill_dir()
    session_path = skill_dir / "reddit_session.json"

    print_step(0, 0, "Session Setup")  # Inline step
    print_colored("Reddit session cookies are needed for scraping.", Colors.CYAN)
    print()

    if session_path.exists():
        print_colored("Existing session found.", Colors.GREEN)
        if confirm("Keep existing session?"):
            return True

    print()
    print_colored("Choose session setup method:", Colors.CYAN)
    print()
    print("  [1] Extract from Chrome (if logged in to Reddit in Chrome)")
    print("  [2] Manual entry (copy from browser DevTools)")
    print("  [3] Skip (you can set up later)")
    print()

    choice = prompt_user("Enter choice", "2")

    if choice == "1":
        return extract_cookies_from_browser()
    elif choice == "2":
        return manual_cookie_entry()
    else:
        print("Session setup skipped. You can run it later with:")
        print(f"  python3 {skill_dir}/get_cookies.py")
        print(f"  or manually create {session_path}")
        return True


def extract_cookies_from_browser() -> bool:
    """Try to extract cookies from Chrome."""
    skill_dir = get_skill_dir()
    get_cookies_script = skill_dir / "get_cookies.py"

    print()
    print("Attempting to extract cookies from Chrome...")
    code, out, err = run_command([str(get_venv_python()), str(get_cookies_script)], cwd=str(skill_dir))

    if code == 0 and "Successfully extracted" in out:
        print_colored("Cookies extracted successfully!", Colors.GREEN)
        return True
    else:
        print_colored("Automatic extraction failed.", Colors.WARNING)
        print("Falling back to manual entry...")
        return manual_cookie_entry()


def manual_cookie_entry() -> bool:
    """Prompt user to manually enter cookies."""
    skill_dir = get_skill_dir()
    session_path = skill_dir / "reddit_session.json"

    print()
    print_colored("Manual Cookie Entry", Colors.CYAN)
    print()
    print("Instructions:")
    print("  1. Open Chrome and log into Reddit (https://www.reddit.com)")
    print("  2. Press F12 to open DevTools")
    print("  3. Go to Application → Cookies → https://www.reddit.com")
    print("  4. Copy the following cookies:")
    print()
    print("     • reddit_session (long JWT token starting with eyJ...)")
    print("     • token_v2       (long JWT token starting with eyJ...)")
    print("     • csrf_token     (short hex string like 76d873...)")
    print()

    reddit_session = prompt_user("Enter reddit_session")
    token_v2 = prompt_user("Enter token_v2")
    csrf_token = prompt_user("Enter csrf_token")

    if not reddit_session or not token_v2 or not csrf_token:
        print_colored("All three cookies are required.", Colors.FAIL)
        return False

    cookies = [
        {"name": "reddit_session", "value": reddit_session},
        {"name": "token_v2", "value": token_v2},
        {"name": "csrf_token", "value": csrf_token}
    ]

    try:
        with open(session_path, 'w') as f:
            json.dump(cookies, f, indent=2)
        print_colored(f"Session saved to {session_path}", Colors.GREEN)
        return True
    except Exception as e:
        print_colored(f"Failed to save session: {e}", Colors.FAIL)
        return False


def install_systemd_service() -> bool:
    """Install systemd service for reddit-scrape."""
    skill_dir = get_skill_dir()
    user = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'root'

    print("Installing systemd service...")

    # Check if running with sudo
    if os.geteuid() != 0:
        print_colored("This step requires sudo privileges.", Colors.WARNING)
        print("Running install-service.sh with sudo...")
        install_script = skill_dir / "install-service.sh"
        code, out, err = run_command(['bash', str(install_script)], sudo=True, capture=False)
        return code == 0

    # We're already root, install directly
    service_content = f"""[Unit]
Description=Reddit Scraper API Server with Auto Auth Refresh
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={skill_dir}
Environment="REDDIT_SESSION_PATH={skill_dir}/reddit_session.json"
Environment="REDDIT_SCRAPE_HOST=127.0.0.1"
Environment="REDDIT_SCRAPE_PORT=8766"
Environment="PLAYWRIGHT_BROWSERS_PATH=0"
ExecStart={skill_dir}/venv/bin/python {skill_dir}/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

    service_path = Path("/etc/systemd/system/reddit-scrape.service")

    try:
        with open(service_path, 'w') as f:
            f.write(service_content)

        run_command(['systemctl', 'daemon-reload'], check=True)
        run_command(['systemctl', 'enable', 'reddit-scrape'], check=True)

        print_colored("Systemd service installed successfully.", Colors.GREEN)
        return True
    except Exception as e:
        print_colored(f"Failed to install service: {e}", Colors.FAIL)
        return False


def start_service() -> bool:
    """Start the reddit-scrape service."""
    print("Starting reddit-scrape service...")

    code, out, err = run_command(['systemctl', 'start', 'reddit-scrape'], sudo=True)
    if code != 0:
        print_colored(f"Failed to start service: {err}", Colors.FAIL)
        return False

    # Wait a moment for service to initialize
    time.sleep(3)

    # Check status
    code, out, err = run_command(['systemctl', 'is-active', 'reddit-scrape'], check=False)
    if code == 0 and 'active' in out:
        print_colored("Service is active.", Colors.GREEN)
        return True
    else:
        print_colored("Service may not be fully started yet.", Colors.WARNING)
        return True  # Don't fail - it might still be starting


def test_installation() -> bool:
    """Test the installation by calling the health endpoint."""
    import urllib.request
    import urllib.error

    print()
    print("Testing installation...")

    host = "127.0.0.1"
    port = 8766

    # Try a few times with delay
    for attempt in range(3):
        try:
            req = urllib.request.Request(f"http://{host}:{port}/health")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                print()
                print_colored("Installation Test Results:", Colors.CYAN)
                print(f"  Server status: {'OK' if data.get('status') == 'ok' else 'ERROR'}")
                print(f"  Session exists: {data.get('session_exists', False)}")
                print(f"  Session valid: {data.get('session_valid', False)}")
                print(f"  Endpoint: {data.get('endpoint', 'N/A')}")

                if data.get('status') == 'ok':
                    print_colored("\n✓ Installation successful!", Colors.GREEN)
                    return True
                else:
                    print_colored("\n⚠ Server running but not healthy", Colors.WARNING)
                    return False

        except urllib.error.URLError as e:
            if attempt < 2:
                print(f"  Attempt {attempt + 1}/3: Server not ready, waiting...")
                time.sleep(3)
            else:
                print_colored(f"\n✗ Cannot connect to server: {e}", Colors.FAIL)
                print("The service may still be starting. Check status with:")
                print("  sudo systemctl status reddit-scrape")
                return False
        except Exception as e:
            print_colored(f"\n✗ Test failed: {e}", Colors.FAIL)
            return False

    return False


def show_completion_message():
    """Show the completion message with usage instructions."""
    skill_dir = get_skill_dir()

    print_colored("""
╔════════════════════════════════════════════════════════════╗
║           Reddit Scrape Setup Complete!                    ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  Your Reddit scraper is now ready to use.                  ║
║                                                            ║
║  Available commands:                                       ║
║    reddit status              - Check server status          ║
║    reddit user <username>     - Get user profile             ║
║    reddit subreddit <name>    - Get subreddit posts          ║
║    reddit post <id>           - Get post with comments       ║
║    reddit search "query"      - Search posts                 ║
║    reddit upvote <id>         - Upvote a post                ║
║    reddit downvote <id>       - Downvote a post              ║
║    reddit comment "text"      - Comment on a post              ║
║    reddit submit "title"      - Create a post                  ║
║    reddit refresh             - Force session refresh        ║
║                                                            ║
║  Service management:                                         ║
║    sudo systemctl status reddit-scrape                       ║
║    sudo systemctl restart reddit-scrape                      ║
║    sudo journalctl -u reddit-scrape -f                       ║
║                                                            ║
║  Configuration files:                                        ║
║    {skill_dir}/.reddit_config.json  - Credentials            ║
║    {skill_dir}/reddit_session.json  - Auth cookies           ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
""".format(skill_dir=skill_dir), Colors.GREEN)


def main():
    """Main wizard flow."""
    total_steps = 6

    # Print welcome banner
    print_colored("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║         Reddit Scrape Setup Wizard                         ║
║         Installs and configures reddit_scrape skill        ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
""", Colors.CYAN + Colors.BOLD)

    skill_dir = get_skill_dir()
    if not skill_dir.exists():
        print_colored(f"Error: Skill directory not found at {skill_dir}", Colors.FAIL)
        sys.exit(1)

    # STEP 1: Check Python version
    print_step(1, total_steps, "Check Python Version")
    if not check_python_version():
        print_colored("Please install Python 3.10 or higher.", Colors.FAIL)
        sys.exit(1)

    # STEP 2: Install dependencies
    print_step(2, total_steps, "Install Dependencies")
    if not check_and_install_dependencies():
        print_colored("Some dependencies failed to install. Continuing anyway...", Colors.WARNING)

    # STEP 3: Set up credentials
    print_step(3, total_steps, "Configure Reddit Credentials")
    if not setup_credentials():
        if not confirm("Continue without credentials?"):
            sys.exit(0)

    # STEP 4: Set up session
    if not setup_session():
        print_colored("Session setup incomplete. You can complete it later.", Colors.WARNING)

    # STEP 5: Install systemd service
    print_step(5, total_steps, "Install Systemd Service")
    if not install_systemd_service():
        print_colored("Failed to install systemd service. You may need to run:", Colors.WARNING)
        print(f"  sudo bash {skill_dir}/install-service.sh")

    # STEP 6: Start service and test
    print_step(6, total_steps, "Start Service & Test")
    if start_service():
        test_installation()
    else:
        print_colored("Service failed to start. Check logs with:", Colors.WARNING)
        print("  sudo journalctl -u reddit-scrape -n 50")

    # Show completion message
    show_completion_message()

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\nWizard interrupted. You can re-run with:", Colors.WARNING)
        print_colored(f"  python3 {get_skill_dir()}/setup_wizard.py", Colors.CYAN)
        sys.exit(0)
    except Exception as e:
        print_colored(f"\n\nError: {e}", Colors.FAIL)
        import traceback
        traceback.print_exc()
        sys.exit(1)
