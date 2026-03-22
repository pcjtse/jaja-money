"""Integration test conftest — starts a Streamlit server with mock data.

The server uses a fake finnhub/anthropic/yfinance that returns pre-built
mock data so tests run fully offline without any real API keys.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[2]
MOCKS_DIR = Path(__file__).parent / "mocks"
STREAMLIT_PORT = 8502  # Use a different port than the default 8501

# Chromium executable — only override when the default playwright browser is
# missing (e.g. local dev with a mismatched playwright version).  In CI,
# playwright install puts the browser in the expected location automatically
# so we leave CHROMIUM_PATH as None and let pytest-playwright find it.
_CHROMIUM_CANDIDATES = [
    "/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome",
    "/root/.cache/ms-playwright/chromium-1208/chrome-linux/chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]

CHROMIUM_PATH: str | None = None
for _c in _CHROMIUM_CANDIDATES:
    try:
        if Path(_c).exists():
            CHROMIUM_PATH = _c
            break
    except (PermissionError, OSError):
        continue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_server(url: str, timeout: int = 60) -> bool:
    """Poll until the server responds or timeout is reached."""
    import urllib.request
    import urllib.error

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Streamlit server fixture (session-scoped — start once per test session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def streamlit_server(tmp_path_factory):
    """Start a Streamlit app process with mocked dependencies.

    Yields the base URL for the running server.
    """
    # Build environment with mocks directory prepended to PYTHONPATH
    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH", "")
    mock_path = str(MOCKS_DIR)
    env["PYTHONPATH"] = f"{mock_path}:{existing_path}" if existing_path else mock_path

    # Use the built-in MockFinnhubAPI (synthetic data, no real API calls).
    # PYTHONPATH mocks still shadow the anthropic module for streaming.
    env["MOCK_DATA"] = "1"
    env["FINNHUB_API_KEY"] = "test_integration_key"
    env["ANTHROPIC_API_KEY"] = "test_integration_key"
    env["AI_BACKEND"] = "sdk"

    # Point jaja-money data dirs to temp locations (don't change HOME —
    # that would break user-installed Python packages)
    tmp_data = tmp_path_factory.mktemp("jaja_data")
    env["JAJA_CACHE_DIR"] = str(tmp_data / "cache")
    env["JAJA_HISTORY_DB"] = str(tmp_data / "history.db")
    env["JAJA_WATCHLIST"] = str(tmp_data / "watchlist.json")
    env["JAJA_ALERTS"] = str(tmp_data / "alerts.json")

    # Headless streamlit config
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_SERVER_PORT"] = str(STREAMLIT_PORT)
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

    # Prefer a Python that has streamlit installed (the pytest venv may not).
    import shutil

    _streamlit_bin = shutil.which("streamlit")
    if _streamlit_bin:
        _python_cmd: list[str] = [_streamlit_bin]
    else:
        # Fall back: find the Python that has streamlit
        _candidates = [
            "/usr/local/bin/python3",
            "/usr/bin/python3",
            sys.executable,
        ]
        _py = next(
            (
                p
                for p in _candidates
                if Path(p).exists()
                and __import__("subprocess")
                .run([p, "-c", "import streamlit"], capture_output=True)
                .returncode
                == 0
            ),
            sys.executable,
        )
        _python_cmd = [_py, "-m", "streamlit"]

    cmd = [
        *_python_cmd,
        "run",
        str(REPO_ROOT / "app.py"),
        "--server.port",
        str(STREAMLIT_PORT),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--server.fileWatcherType",
        "none",
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    base_url = f"http://localhost:{STREAMLIT_PORT}"
    health_url = f"{base_url}/_stcore/health"

    try:
        ok = _wait_for_server(health_url, timeout=90)
        if not ok:
            stdout = proc.stdout.read() if proc.stdout else ""
            stderr = proc.stderr.read() if proc.stderr else ""
            proc.kill()
            raise RuntimeError(
                f"Streamlit server failed to start within 90s.\n"
                f"stdout: {stdout[:2000]}\nstderr: {stderr[:2000]}"
            )
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------------------------------------------------------------------
# Playwright fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Pass explicit chromium executable path if the default is missing."""
    args = dict(browser_type_launch_args)
    if CHROMIUM_PATH:
        args["executable_path"] = CHROMIUM_PATH
    args["args"] = args.get("args", []) + ["--no-sandbox", "--disable-dev-shm-usage"]
    return args


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Extend browser context with viewport and locale."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
        "locale": "en-US",
    }


@pytest.fixture
def app_page(page, streamlit_server):
    """Navigate to the Streamlit app and return a configured Playwright page."""
    page.set_default_timeout(30_000)
    page.goto(streamlit_server)
    # Wait for Streamlit app shell to appear
    page.wait_for_selector('[data-testid="stApp"]', timeout=30_000)
    # Wait for at least the sidebar navigation to be populated
    page.wait_for_selector('[data-testid="stSidebar"]', timeout=30_000)
    # Wait for the Analyze button (confirms sidebar custom content is rendered)
    try:
        page.wait_for_selector('button:has-text("Analyze")', timeout=20_000)
    except Exception:
        pass  # Gracefully continue if not found — individual tests will assert
    # Give Streamlit a moment to finish rendering all widgets
    page.wait_for_timeout(2000)
    return page
