#!/usr/bin/env python3
"""
Setup script — configures the MCP server for Claude Desktop and Claude Code.
Run once after installing dependencies:  python setup_claude.py
"""

import json
import os
import sys
import shutil
import subprocess

SERVER_DIR  = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(SERVER_DIR, "server.py")
PYTHON      = sys.executable

MCP_ENTRY = {
    "command": PYTHON,
    "args":    [SERVER_PATH],
    "env":     {"DB_MODE": "demo"},
}

# ── Claude Desktop ─────────────────────────────────────────────────────────────
DESKTOP_CONFIG_PATHS = [
    os.path.expandvars(r"%APPDATA%\Claude\claude_desktop_config.json"),            # Windows
    os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json"),  # macOS
    os.path.expanduser("~/.config/claude/claude_desktop_config.json"),             # Linux
]

def configure_desktop():
    for cfg_path in DESKTOP_CONFIG_PATHS:
        if os.path.exists(os.path.dirname(cfg_path)):
            if os.path.exists(cfg_path):
                with open(cfg_path) as f:
                    cfg = json.load(f)
            else:
                cfg = {}
            cfg.setdefault("mcpServers", {})
            cfg["mcpServers"]["customer-master-data-ai"] = MCP_ENTRY
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)
            print(f"[OK] Claude Desktop configured: {cfg_path}")
            return True
    print("[SKIP] Claude Desktop config not found — install Claude Desktop first.")
    return False


# ── Claude Code ────────────────────────────────────────────────────────────────
CODE_CONFIG_PATH = os.path.expanduser("~/.claude/mcp.json")

def configure_code():
    if os.path.exists(CODE_CONFIG_PATH):
        with open(CODE_CONFIG_PATH) as f:
            cfg = json.load(f)
    else:
        os.makedirs(os.path.dirname(CODE_CONFIG_PATH), exist_ok=True)
        cfg = {}

    cfg.setdefault("mcpServers", {})
    cfg["mcpServers"]["customer-master-data-ai"] = MCP_ENTRY
    with open(CODE_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[OK] Claude Code configured: {CODE_CONFIG_PATH}")


# ── Install deps ───────────────────────────────────────────────────────────────
def install_deps():
    req = os.path.join(SERVER_DIR, "requirements.txt")
    print("[..] Installing Python dependencies...")
    result = subprocess.run(
        [PYTHON, "-m", "pip", "install", "-r", req, "-q"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[ERROR] pip install failed:\n{result.stderr}")
        sys.exit(1)
    print("[OK] Dependencies installed")


# ── Test server import ─────────────────────────────────────────────────────────
def test_import():
    print("[..] Testing server startup...")
    result = subprocess.run(
        [PYTHON, "-c",
         "import sys; sys.path.insert(0,'" + SERVER_DIR.replace("\\","\\\\") + "'); "
         "import demo_db; demo_db.init_db(); "
         "from agents.deduplication import find_duplicates; "
         "r = find_duplicates(); "
         "print('Duplicate groups found:', r['total_duplicate_groups'])"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[ERROR] Import test failed:\n{result.stderr}")
        return False
    print(f"[OK] Server test: {result.stdout.strip()}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("  Customer Master Data AI — Setup")
    print("=" * 60)
    install_deps()
    test_import()
    configure_code()
    configure_desktop()
    print()
    print("=" * 60)
    print("  DONE!")
    print("  Restart Claude Desktop / Claude Code to load the server.")
    print("  Try asking: 'Find duplicate customer parties'")
    print("=" * 60)
