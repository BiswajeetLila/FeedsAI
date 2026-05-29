"""
LLM CLI wrapper — async subprocess bridge to claude / gemini CLIs.

Design notes
------------
* Uses asyncio.create_subprocess_exec (shell=False) always.
* Prompt delivered via stdin to prevent shell-injection.
* Session-level _cli_available dict avoids re-checking a missing CLI.
* Preferred order: claude → gemini.
* Retry / fallback policy:
    - returncode 127 / FileNotFoundError  → permanent session mark, gemini fallback,
                                            returned error='cli_not_found'
    - returncode 1 (API error)             → retry once with same model, then gemini
                                            fallback, returned error='api_error'
    - asyncio.TimeoutError                 → kill proc, return immediately with
                                            error='timeout' (no gemini fallback)
    - empty stdout                         → bad_output error (no fallback)

When gemini is used as a fallback, the original error kind is preserved in the
returned LLMResult so callers know why the primary model was skipped.
"""

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


def _record(model: str, error: str | None, latency_s: float) -> None:
    """Telemetry hook — lazy import to avoid cycles during testing."""
    try:
        from app import observability
        observability.record_llm(model, error, latency_s)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

ErrorKind = Literal["cli_not_found", "api_error", "bad_output", "timeout", "quota_exhausted"]

# Substrings that indicate a hard, session-long backend outage. When matched in
# stderr we stop trying that model until the process restarts.
_QUOTA_MARKERS = ("QUOTA_EXHAUSTED", "TerminalQuotaError", "exhausted your capacity")

ModelName = Literal["claude", "gemini"]


@dataclass(frozen=True)
class LLMResult:
    text: str
    model_used: ModelName
    error: ErrorKind | None  # None = success


# ---------------------------------------------------------------------------
# Session-level CLI availability cache
# ---------------------------------------------------------------------------

_cli_available: dict[str, bool] = {"claude": True, "gemini": True}

# ---------------------------------------------------------------------------
# CLI command builders
# ---------------------------------------------------------------------------

def _resolve_binary(name: str) -> str | None:
    """Honor PATHEXT (.cmd/.exe/etc.) — asyncio.create_subprocess_exec doesn't."""
    return shutil.which(name)


def _build_command(model: ModelName, prompt: str) -> tuple[list[str], bytes | None]:
    """Return (argv, stdin_bytes). stdin_bytes is None for arg-based prompt models."""
    if model == "claude":
        binary = _resolve_binary("claude") or "claude"
        # claude takes prompt via stdin
        return ([binary, "--print", "--output-format", "text"], prompt.encode())
    elif model == "gemini":
        binary = _resolve_binary("gemini") or "gemini"
        # gemini takes prompt via --prompt arg; stdin not used in headless mode
        return (
            [binary, "--skip-trust", "--prompt", prompt, "--output-format", "text"],
            None,
        )
    raise ValueError(f"Unknown model: {model}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_cli(
    model: ModelName,
    prompt: str,
    timeout: int,
) -> tuple[int, bytes, bytes]:
    """
    Launch the CLI for *model*, deliver prompt (stdin or arg per model),
    return (returncode, stdout, stderr).

    Raises:
        FileNotFoundError     — executable not on PATH
        asyncio.TimeoutError  — communicate timed out; process killed before raising
    """
    args, stdin_bytes = _build_command(model, prompt)
    logger.debug("Spawning %s CLI", model)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_bytes),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()  # reap child so it doesn't become a zombie
        raise

    return proc.returncode, stdout, stderr


# ---------------------------------------------------------------------------
# Model-level call (handles its own retry for api_error)
# ---------------------------------------------------------------------------


_NO_FALLBACK_ERRORS: frozenset[ErrorKind] = frozenset({"timeout", "bad_output"})
_FALLBACK_ERRORS: frozenset[ErrorKind] = frozenset({"cli_not_found", "api_error", "quota_exhausted"})


async def _call_model_once(
    model: ModelName,
    prompt: str,
    timeout: int,
) -> LLMResult:
    """
    Single attempt to call *model*. No retry logic here.
    Returns an LLMResult whose model_used is always *model*.
    """
    started = time.monotonic()

    def _done(result: LLMResult) -> LLMResult:
        _record(model, result.error, time.monotonic() - started)
        return result

    try:
        returncode, stdout, stderr = await _run_cli(model, prompt, timeout)
    except FileNotFoundError:
        logger.warning("%s CLI not found (FileNotFoundError); marking unavailable", model)
        _cli_available[model] = False
        return _done(LLMResult(text="", model_used=model, error="cli_not_found"))
    except asyncio.TimeoutError:
        logger.warning("%s CLI timed out after %ds", model, timeout)
        return _done(LLMResult(text="", model_used=model, error="timeout"))

    if returncode == 127:
        logger.warning("%s CLI returned 127 (not found); marking unavailable", model)
        _cli_available[model] = False
        return _done(LLMResult(text="", model_used=model, error="cli_not_found"))

    if returncode == 1:
        stderr_text = stderr.decode(errors="replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr)
        if any(marker in stderr_text for marker in _QUOTA_MARKERS):
            logger.warning(
                "%s CLI quota exhausted; marking unavailable for this session. stderr=%s",
                model, stderr_text[:500],
            )
            _cli_available[model] = False
            return _done(LLMResult(text="", model_used=model, error="quota_exhausted"))
        logger.warning("%s CLI returned API error (rc=1); stderr=%s", model, stderr_text[:2000])
        return _done(LLMResult(text="", model_used=model, error="api_error"))

    if returncode != 0:
        logger.warning("%s CLI unexpected returncode %d", model, returncode)
        return _done(LLMResult(text="", model_used=model, error="api_error"))

    text = stdout.decode(errors="replace").strip()
    if not text:
        logger.warning("%s CLI returned empty output", model)
        return _done(LLMResult(text="", model_used=model, error="bad_output"))

    logger.debug("%s CLI succeeded (%d chars)", model, len(text))
    return _done(LLMResult(text=text, model_used=model, error=None))


async def _call_model(
    model: ModelName,
    prompt: str,
    timeout: int,
) -> LLMResult:
    """
    Call *model* with one automatic retry on api_error.
    """
    result = await _call_model_once(model, prompt, timeout)
    if result.error == "api_error":
        logger.debug("Retrying %s once after API error", model)
        result = await _call_model_once(model, prompt, timeout)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_llm(
    prompt: str,
    timeout: int = 120,
    prefer: ModelName = "claude",
) -> LLMResult:
    """
    Call preferred LLM CLI with *prompt*. Falls back to the other model on
    cli_not_found / api_error.

    Args:
        prompt: full prompt text.
        timeout: per-call timeout seconds.
        prefer: which model to try first ("claude" default; "gemini" for callers
            who want gemini-primary like summarization).

    Returns LLMResult. .error is None on any clean success — including a
    successful fallback after the primary failed. model_used reflects which
    model produced the text.
    """
    primary: ModelName = prefer
    secondary: ModelName = "gemini" if primary == "claude" else "claude"

    # ---- Attempt primary (if available) -----------------------------------
    if _cli_available.get(primary, True):
        result = await _call_model(primary, prompt, timeout)

        if result.error is None:
            return result

        if result.error in _NO_FALLBACK_ERRORS:
            return result

        logger.warning(
            "%s failed with error=%r; falling back to %s",
            primary, result.error, secondary,
        )

        if _cli_available.get(secondary, True):
            # If fallback succeeds, return its result verbatim (error=None) so
            # callers don't discard a working summary. If it also fails, surface
            # the fallback's error since that's the more recent failure.
            return await _call_model(secondary, prompt, timeout)

        return LLMResult(text="", model_used=secondary, error=result.error)

    # ---- Primary unavailable → straight to secondary ----------------------
    if _cli_available.get(secondary, True):
        return await _call_model(secondary, prompt, timeout)

    logger.error("No LLM CLI available in this session")
    return LLMResult(text="", model_used=secondary, error="cli_not_found")
