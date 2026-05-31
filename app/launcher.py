"""
Small helpers for user-facing app launchers.
"""
from collections.abc import Callable
import socket
import time
from urllib.parse import urlsplit

import httpx

from app.onboarding import setup_required


def choose_start_path(setup_required_fn: Callable[[], bool] = setup_required) -> str:
    return "/setup" if setup_required_fn() else "/"


def choose_start_url(
    port: int = 8000,
    setup_required_fn: Callable[[], bool] = setup_required,
) -> str:
    return f"http://127.0.0.1:{port}{choose_start_path(setup_required_fn)}"


def find_available_port(preferred: int = 8000, host: str = "127.0.0.1") -> int:
    for port in range(preferred, preferred + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def server_is_running(port: int, host: str = "127.0.0.1") -> bool:
    try:
        response = httpx.get(f"http://{host}:{port}/healthz", timeout=1.5)
        return response.status_code == 200
    except Exception:
        return False


def wait_for_server(port: int, host: str = "127.0.0.1", timeout_seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server_is_running(port, host):
            return True
        time.sleep(0.25)
    return False


def build_launch_message(start_url: str) -> str:
    parsed = urlsplit(start_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return "\n".join([
        f"FeedsAI app: {start_url}",
        f"Status page: {base_url}/status",
        f"Logs page: {base_url}/logs",
        "Close this window to stop FeedsAI.",
    ])
