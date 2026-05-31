"""
Windows packaged-app launcher.

This starts the local FastAPI server, opens the browser, and exits cleanly when
the app window/process is closed. PyInstaller should use this module as the
entrypoint for FeedsAI.exe.
"""
from __future__ import annotations

import logging
import signal
import threading
import webbrowser

import uvicorn

from app.launcher import (
    build_launch_message,
    choose_start_url,
    find_available_port,
    wait_for_server,
)

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    port = find_available_port(8000)
    start_url = choose_start_url(port)
    message = build_launch_message(start_url)
    print(message, flush=True)

    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    def _open_browser_when_ready() -> None:
        if wait_for_server(port):
            webbrowser.open(start_url)
        else:
            logger.warning("Server did not become ready before browser timeout")

    opener = threading.Thread(target=_open_browser_when_ready, daemon=True)
    opener.start()

    def _stop_server(_signum, _frame) -> None:
        server.should_exit = True

    signal.signal(signal.SIGINT, _stop_server)
    signal.signal(signal.SIGTERM, _stop_server)

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
