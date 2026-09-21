"""
Achilles CDP Agent — Autonomous Agentic Chrome DevTools Protocol (CDP) Bridge & Security/API Engine
"""
import os
import sys

# Silence Node.js deprecation warnings inside Playwright driver
os.environ.setdefault("NODE_OPTIONS", "--no-deprecation")

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

__version__ = "2.1.0"
__author__ = "Pedro Lucas Reis & Reoli Open Source"

