#!/usr/bin/env python3
"""Start the interface server and open the UI in Chrome/Chromium."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from shutil import which

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
SERVER_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/"
BROWSER_URL = f"http://localhost:{DEFAULT_PORT}/"


def find_chrome() -> list[str] | None:
    """Return a Chrome/Chromium launch command if available."""

    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ]
    for candidate in candidates:
        path = which(candidate)
        if path:
            return [path]
    return None


def wait_for_server(server: subprocess.Popen, url: str, timeout: float = 15.0) -> None:
    """Block until the interface server responds or fail with a helpful error."""

    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        if server.poll() is not None:
            raise RuntimeError(
                f"Interface server exited early with code {server.returncode}."
            )
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except urllib.error.URLError as exc:  # server not yet ready
            last_error = exc
            time.sleep(0.5)
    raise TimeoutError(
        f"Timed out waiting for interface server at {url}: {last_error}"
    )


def open_browser(url: str) -> None:
    """Open the UI in Chrome/Chromium if available, otherwise print instructions."""

    browser_cmd = find_chrome()
    if not browser_cmd:
        print("Chrome/Chromium not found. Open the UI manually at", url)
        return

    try:
        subprocess.Popen(
            browser_cmd + [f"--app={url}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Opened Chrome/Chromium with the interface UI.")
    except OSError as exc:
        print(f"Failed to launch Chrome/Chromium: {exc}. Open the UI manually at {url}")


def main() -> int:
    server_cmd = [sys.executable, str(Path(__file__).parent / "scripts" / "interface_server.py")]
    print("Starting interface server...", " ".join(server_cmd))
    server = subprocess.Popen(server_cmd)

    try:
        wait_for_server(server, SERVER_URL)
    except Exception as exc:
        server.terminate()
        server.wait(timeout=5)
        print(exc)
        return 1

    print(f"Interface server is ready at {BROWSER_URL}")
    open_browser(BROWSER_URL)

    try:
        server.wait()
    except KeyboardInterrupt:
        server.terminate()
    return 0


if __name__ == "__main__":  # pragma: no cover - manual launcher
    raise SystemExit(main())
