#!/usr/bin/env python3
"""
Reddit Scrape Setup Wizard - Fully Automated
Creates venv, installs deps, sets up cookies, installs systemd service.
"""

import os
import sys
import json
import subprocess
import time
import shutil
import socket
from pathlib import Path
from typing import List, Tuple, Optional


class Colors:
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'


def printc(text: str, color: str = ""):
    print(f"{color}{text}{Colors.END}" if color else text)


def run(cmd: List[str], capture: bool = True, sudo: bool = False, cwd: str = None, timeout: int = 60) -> Tuple[int, str, str]:
    if sudo and os.geteuid() != 0:
        cmd = ['sudo'] + cmd
    try:
        result = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def get_skill_dir() -> Path:
    return Path(__file__).parent.resolve()


def find_python() -> Optional[Path]:
    for py in ['python3.12', 'python3.11', 'python3.10', 'python3']:
        code, out, _ = run([py, '--version'], capture=True)
        if code == 0:
            try:
                ver = out.strip().split()[1]
                major, minor = map(int, ver.split('.')[:2])
                if major == 3 and minor >= 10:
                    which_path = shutil.which(py)
                    if which_path:
                        return Path(which_path)
                    return Path(f'/usr/bin/{py}')
            except:
                pass
    return None


def find_existing_venv() -> Optional[Path]:
    home = Path.home()
    skill_dir = get_skill_dir()

    search_paths = [
        home / ".openclaw" / "skills" / "twitter_scrape" / "venv",
        home / ".openclaw" / "skills" / "reddit_scrape" / "venv",
        home / ".openclaw" / "skills" / "ebay_scrape" / "venv",
        home / "venv",
        home / ".venv",
        Path("/opt/venv"),
        Path("/var/venv"),
        skill_dir.parent / "venv",
        skill_dir.parent / ".venv",
    ]

    env_venv = os.environ.get('VIRTUAL_ENV')
    if env_venv:
        search_paths.insert(0, Path(env_venv))

    for venv_path in search_paths:
        if not venv_path.exists():
            continue
        python_exe = venv_path / "bin" / "python"
        if not python_exe.exists():
            python_exe = venv_path / "Scripts" / "python.exe"
        if python_exe.exists():
            code, out, _ = run([str(python_exe), '--version'], capture=True)
            if code == 0:
                try:
                    ver = out.strip().split()[1]
                    major, minor = map(int, ver.split('.')[:2])
                    if major == 3 and minor >= 10:
                        printc(f"Found existing venv: {venv_path} (Python {ver})", Colors.CYAN)
                        return python_exe
                except:
                    pass
    return None


def setup_venv(skill_dir: Path) -> Path:
    venv = skill_dir / "venv"
    python = venv / "bin" / "python"

    if venv.exists() and python.exists():
        code, out, _ = run([str(python), '--version'], capture=True)
        if code == 0:
            try:
                ver = out.strip().split()[1]
                major, minor = map(int, ver.split('.')[:2])
                if major == 3 and minor >= 10:
                    printc(f"Using existing venv: {venv}", Colors.GREEN)
                    return python
            except:
                pass

    existing_python = find_existing_venv()
    if existing_python:
        printc(f"Linking to existing venv: {existing_python.parent.parent}", Colors.CYAN)
        if venv.exists():
            venv.unlink() if venv.is_symlink() else shutil.rmtree(venv)
        venv.symlink_to(existing_python.parent.parent)
        return existing_python

    py = find_python()
    if not py:
        printc("Python 3.10+ not found. Install python3.10 or higher.", Colors.FAIL)
        sys.exit(1)

    printc(f"Creating venv with {py}...", Colors.CYAN)
    code, _, err = run([str(py), '-m', 'venv', str(venv)])
    if code != 0:
        printc(f"Failed to create venv: {err}", Colors.FAIL)
        sys.exit(1)

    return python


def install_deps(python: Path):
    pip = python.parent / "pip"
    printc("Installing dependencies (this may take a few minutes)...", Colors.CYAN)

    deps = ['rnet', 'playwright', 'playwright-stealth', 'xvfbwrapper']
    for pkg in deps:
        printc(f" Installing {pkg}...", Colors.CYAN)
        args = [str(pip), 'install', pkg, '--pre'] if pkg == 'rnet' else [str(pip), 'install', pkg]
        run(args, capture=True)

    printc("Installing Chromium...", Colors.CYAN)
    run([str(python), '-m', 'playwright', 'install', 'chromium'], capture=True)
    printc("Dependencies installed.", Colors.GREEN)


def is_chrome_debug_port_open() -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', 9222))
        sock.close()
        return result == 0
    except:
        return False


def start_chrome_debug():
    printc("\nChrome debugging port 9222 not found.", Colors.WARNING)
    printc("Please start Chrome with remote debugging:", Colors.CYAN)
    printc("\n  google-chrome --remote-debugging-port=9222 &", Colors.BOLD)
    printc("\nOr if already running, restart it with the flag.", Colors.CYAN)

    resp = input("\nHave you started Chrome with debugging? [y/N]: ").strip().lower()
    if resp != 'y':
        printc("Cannot continue without Chrome debugging port.", Colors.FAIL)
        sys.exit(1)

    for i in range(10):
        if is_chrome_debug_port_open():
            printc("Chrome debugging port detected.", Colors.GREEN)
            return True
        time.sleep(1)

    printc("Chrome debugging port still not available.", Colors.FAIL)
    sys.exit(1)


def get_cookies_manual(skill_dir: Path) -> bool:
    printc("\n=== Cookie Setup ===", Colors.CYAN)
    printc("1. Open Chrome and log into reddit.com")
    printc("2. Press F12 -> Application -> Cookies -> https://www.reddit.com")
    printc("3. Copy these cookies:\n")

    reddit_session = input("reddit_session (JWT starting eyJ...): ").strip()
    token_v2 = input("token_v2 (JWT starting eyJ...): ").strip()
    csrf = input("csrf_token (hex string): ").strip()

    if not all([reddit_session, token_v2, csrf]):
        printc("All cookies required.", Colors.FAIL)
        return False

    cookies = [
        {"name": "reddit_session", "value": reddit_session},
        {"name": "token_v2", "value": token_v2},
        {"name": "csrf_token", "value": csrf}
    ]

    session_path = skill_dir / "reddit_session.json"
    with open(session_path, 'w') as f:
        json.dump(cookies, f, indent=2)
    os.chmod(session_path, 0o600)
    printc(f"Session saved.", Colors.GREEN)
    return True


def install_service(skill_dir: Path, python: Path):
    user = os.environ.get('SUDO_USER') or os.environ.get('USER') or os.getlogin()

    service = f"""[Unit]
Description=Reddit Scraper API
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={skill_dir}
Environment="REDDIT_SESSION_PATH={skill_dir}/reddit_session.json"
Environment="REDDIT_SCRAPE_HOST=127.0.0.1"
Environment="REDDIT_SCRAPE_PORT=8766"
Environment="PLAYWRIGHT_BROWSERS_PATH=0"
ExecStart={python} {skill_dir}/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

    temp = Path("/tmp/reddit-scrape.service")
    temp.write_text(service)

    code, _, err = run(['cp', str(temp), '/etc/systemd/system/reddit-scrape.service'], sudo=True)
    if code != 0:
        printc(f"Failed to install service: {err}", Colors.FAIL)
        return False

    run(['systemctl', 'daemon-reload'], sudo=True)
    run(['systemctl', 'enable', 'reddit-scrape'], sudo=True)
    printc("Service installed.", Colors.GREEN)
    return True


def start_service():
    printc("Starting service...", Colors.CYAN)
    run(['systemctl', 'stop', 'reddit-scrape'], sudo=True, capture=True)
    time.sleep(1)
    run(['systemctl', 'start', 'reddit-scrape'], sudo=True)
    time.sleep(3)

    code, out, _ = run(['systemctl', 'is-active', 'reddit-scrape'], sudo=True)
    if 'active' in out:
        printc("Service running.", Colors.GREEN)
        return True
    return False


def test_server():
    import urllib.request
    for i in range(5):
        try:
            req = urllib.request.Request("http://127.0.0.1:8766/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                if data.get('status') == 'ok':
                    printc("Server is healthy.", Colors.GREEN)
                    return True
        except:
            time.sleep(2)
    return False


def create_cli_symlink(skill_dir: Path):
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)

    reddit_cli = skill_dir / "reddit"
    link = local_bin / "reddit"

    if link.exists() or link.is_symlink():
        link.unlink()

    if reddit_cli.exists():
        link.symlink_to(reddit_cli)
        printc(f"CLI available at {link}", Colors.GREEN)

    for profile in [Path.home() / ".bashrc", Path.home() / ".zshrc"]:
        if profile.exists():
            content = profile.read_text()
            if '.local/bin' not in content:
                with open(profile, 'a') as f:
                    f.write('\nexport PATH="$HOME/.local/bin:$PATH"\n')


def main():
    skill_dir = get_skill_dir()
    printc("="*60, Colors.CYAN)
    printc(" Reddit Scrape Setup", Colors.BOLD + Colors.CYAN)
    printc("="*60, Colors.CYAN)

    # Step 1: Setup venv
    python = setup_venv(skill_dir)
    printc(f"Using Python: {python}", Colors.GREEN)

    # Step 2: Install deps
    install_deps(python)

    # Step 3: Check Chrome debugging port
    if not is_chrome_debug_port_open():
        start_chrome_debug()
    else:
        printc("Chrome debugging port 9222 is active.", Colors.GREEN)

    # Step 4: Get cookies (manual only)
    session_path = skill_dir / "reddit_session.json"
    if session_path.exists():
        printc("Existing session found.", Colors.GREEN)
        resp = input("Update cookies? [y/N]: ").strip().lower()
        if resp == 'y':
            if not get_cookies_manual(skill_dir):
                printc("Cookie setup failed.", Colors.FAIL)
                sys.exit(1)
    else:
        if not get_cookies_manual(skill_dir):
            printc("Cookie setup failed.", Colors.FAIL)
            sys.exit(1)

    # Step 5: Install systemd service
    if install_service(skill_dir, python):
        start_service()
        test_server()

    # Step 6: Create CLI symlink
    create_cli_symlink(skill_dir)

    printc("\n" + "="*60, Colors.GREEN)
    printc(" Setup Complete!", Colors.BOLD + Colors.GREEN)
    printc("="*60, Colors.GREEN)
    printc("\nCommands:", Colors.CYAN)
    printc(" reddit status - Check server")
    printc(" reddit user <name> - Get user profile")
    printc(" reddit subreddit <name> - Get posts")
    printc("\nService:", Colors.CYAN)
    printc(" sudo systemctl status reddit-scrape")
    printc("="*60, Colors.GREEN)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        printc("\nInterrupted.", Colors.WARNING)
        sys.exit(0)
    except Exception as e:
        printc(f"\nError: {e}", Colors.FAIL)
        import traceback
        traceback.print_exc()
