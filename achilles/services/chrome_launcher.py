"""Descoberta e partida local de Chrome ou Edge para sessões CDP."""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def profile_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Achilles"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Achilles"
    else:
        base = Path.home() / ".config" / "achilles"
    browser = os.environ.get("ACHILLES_BROWSER", "chrome").lower()
    target = base / ("edge_profile" if browser == "edge" else "chrome_profile")
    target.mkdir(parents=True, exist_ok=True)
    return target


def cdp_available(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def chrome_binary() -> Optional[str]:
    preferred = os.environ.get("ACHILLES_BROWSER", "chrome").lower()
    if preferred not in ("chrome", "edge"):
        preferred = "chrome"
    if sys.platform == "win32":
        chrome_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        edge_candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif sys.platform == "darwin":
        chrome_candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        edge_candidates = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    else:
        chrome_candidates = []
        edge_candidates = []
    candidates = edge_candidates if preferred == "edge" else chrome_candidates
    names = ("microsoft-edge", "microsoft-edge-stable") if preferred == "edge" else (
        "google-chrome", "google-chrome-stable", "chromium-browser", "chromium"
    )
    for name in names:
        executable = shutil.which(name)
        if executable:
            candidates.append(executable)
    return next((path for path in candidates if os.path.isfile(path)), None)


def ensure_chrome_running(port: int, timeout_s: float = 8.0) -> bool:
    """Nunca escreve em stdout; retorna se o endpoint ficou disponível."""
    if cdp_available(port):
        return True
    executable = chrome_binary()
    if executable is None:
        return False
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        subprocess.Popen(
            [
                executable,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir()}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
        )
    except OSError:
        return False
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if cdp_available(port):
            return True
        time.sleep(0.1)
    return cdp_available(port)
