"""
app/observability.py
Process-level telemetry: uptime, request counters, LLM call stats, and an
in-process ring buffer log handler so the /logs page can tail without hitting
disk.

Also wires a RotatingFileHandler at data/server.log so the user can tail in
a separate terminal window.
"""
from __future__ import annotations

import collections
import logging
import logging.handlers
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Boot timestamp (monotonic for uptime, wall for display)
# ---------------------------------------------------------------------------

BOOT_MONOTONIC: float = time.monotonic()
BOOT_WALL: float = time.time()


# ---------------------------------------------------------------------------
# Ring buffer log handler
# ---------------------------------------------------------------------------

_RING_CAPACITY = 300
_ring: collections.deque[str] = collections.deque(maxlen=_RING_CAPACITY)
_ring_lock = threading.Lock()


class RingBufferHandler(logging.Handler):
    """Stores the last _RING_CAPACITY formatted log records in memory."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = self.format(record)
            with _ring_lock:
                _ring.append(msg)
        except Exception:
            self.handleError(record)


def tail_logs(n: int = 200) -> list[str]:
    """Return the last n log lines (oldest first)."""
    with _ring_lock:
        if n >= len(_ring):
            return list(_ring)
        return list(_ring)[-n:]


# ---------------------------------------------------------------------------
# Request counters
# ---------------------------------------------------------------------------

_metrics_lock = threading.Lock()


@dataclass
class RequestStats:
    total: int = 0
    by_status: dict[int, int] = field(default_factory=lambda: collections.defaultdict(int))
    last_path: str = ""
    last_status: int = 0
    last_ts: float = 0.0


request_stats = RequestStats()


def record_request(path: str, status: int) -> None:
    with _metrics_lock:
        request_stats.total += 1
        request_stats.by_status[status] = request_stats.by_status.get(status, 0) + 1
        request_stats.last_path = path
        request_stats.last_status = status
        request_stats.last_ts = time.time()


# ---------------------------------------------------------------------------
# LLM call counters
# ---------------------------------------------------------------------------


@dataclass
class LLMStats:
    calls: int = 0
    successes: int = 0
    errors: dict[str, int] = field(default_factory=dict)
    last_error: str = ""
    last_ts: float = 0.0
    total_latency_s: float = 0.0


_llm_stats: dict[str, LLMStats] = {
    "claude": LLMStats(),
    "gemini": LLMStats(),
}


def record_llm(model: str, error: str | None, latency_s: float) -> None:
    with _metrics_lock:
        s = _llm_stats.setdefault(model, LLMStats())
        s.calls += 1
        s.total_latency_s += latency_s
        s.last_ts = time.time()
        if error is None:
            s.successes += 1
        else:
            s.errors[error] = s.errors.get(error, 0) + 1
            s.last_error = error


def llm_snapshot() -> dict[str, dict]:
    with _metrics_lock:
        out: dict[str, dict] = {}
        for model, s in _llm_stats.items():
            avg = (s.total_latency_s / s.calls) if s.calls else 0.0
            out[model] = {
                "calls": s.calls,
                "successes": s.successes,
                "errors": dict(s.errors),
                "last_error": s.last_error,
                "avg_latency_s": round(avg, 2),
                "last_ts": s.last_ts,
            }
        return out


# ---------------------------------------------------------------------------
# Fetch-cycle state — exposed on /status so the user can see when a fetch
# is running and trigger one manually.
# ---------------------------------------------------------------------------


@dataclass
class FetchState:
    in_progress: bool = False
    started_at: float = 0.0   # wall time
    finished_at: float = 0.0  # wall time of last finish
    last_summary: str = ""    # short result string
    last_error: str = ""


fetch_state = FetchState()


def fetch_started() -> None:
    with _metrics_lock:
        fetch_state.in_progress = True
        fetch_state.started_at = time.time()


def fetch_finished(summary: str = "", error: str = "") -> None:
    with _metrics_lock:
        fetch_state.in_progress = False
        fetch_state.finished_at = time.time()
        fetch_state.last_summary = summary
        fetch_state.last_error = error


# ---------------------------------------------------------------------------
# Uptime helper
# ---------------------------------------------------------------------------


def uptime_seconds() -> float:
    return time.monotonic() - BOOT_MONOTONIC


def format_uptime() -> str:
    s = int(uptime_seconds())
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    mins, secs = divmod(s, 60)
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m {secs}s"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


# ---------------------------------------------------------------------------
# Wire handlers into root logger
# ---------------------------------------------------------------------------


def install_handlers(log_dir: Path) -> Path:
    """
    Attach the ring-buffer handler and a rotating file handler to the root
    logger. Idempotent — safe to call multiple times. Returns the log file
    path so callers can show it to the user.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "server.log"

    root = logging.getLogger()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
        ring = RingBufferHandler()
        ring.setFormatter(fmt)
        ring.setLevel(logging.INFO)
        root.addHandler(ring)

    if not any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and getattr(h, "baseFilename", "") == str(log_path)
        for h in root.handlers
    ):
        fh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        fh.setLevel(logging.INFO)
        root.addHandler(fh)

    # Also ensure uvicorn loggers propagate so we capture access lines.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.propagate = True

    return log_path
