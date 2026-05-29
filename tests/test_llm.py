"""
Tests for app/llm.py — TDD written before implementation.

All subprocess calls are mocked; no real CLI is invoked.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

import app.llm as llm_module
from app.llm import call_llm, LLMResult, _cli_available


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_proc(returncode: int, stdout: bytes = b"", stderr: bytes = b""):
    """Return a mock process with the given returncode and communicate output."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


@pytest.fixture(autouse=True)
def reset_cli_cache():
    """Reset the session-level CLI availability cache before every test."""
    _cli_available["claude"] = True
    _cli_available["gemini"] = True
    yield
    _cli_available["claude"] = True
    _cli_available["gemini"] = True


# ---------------------------------------------------------------------------
# Test 1 — Happy path: claude returns text with returncode=0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_claude():
    proc = make_proc(returncode=0, stdout=b"hello world\n")

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        result = await call_llm("test prompt")

    assert result == LLMResult(text="hello world", model_used="claude", error=None)
    # Must use create_subprocess_exec (not shell)
    mock_exec.assert_called_once()
    # 'shell' keyword must NOT be in the call (create_subprocess_exec has no shell param)
    _, kwargs = mock_exec.call_args
    assert "shell" not in kwargs


# ---------------------------------------------------------------------------
# Test 2 — Claude CLI not found (returncode 127) → gemini fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_not_found_falls_back_to_gemini():
    claude_proc = make_proc(returncode=127, stdout=b"", stderr=b"claude: command not found")
    gemini_proc = make_proc(returncode=0, stdout=b"gemini answer\n")

    side_effects = [claude_proc, gemini_proc]

    with patch("asyncio.create_subprocess_exec", side_effect=side_effects) as mock_exec:
        result = await call_llm("test prompt")

    # Session cache must mark claude unavailable
    assert _cli_available["claude"] is False

    assert result.model_used == "gemini"
    # Successful fallback: error must be None so callers don't discard a working answer.
    assert result.error is None
    assert result.text == "gemini answer"

    # Two subprocess calls: first claude (127), then gemini
    assert mock_exec.call_count == 2


# ---------------------------------------------------------------------------
# Test 3 — Claude API error (returncode 1) → retry once, then gemini
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_api_error_retry_then_gemini():
    claude_proc_1 = make_proc(returncode=1, stdout=b"", stderr=b"API error")
    claude_proc_2 = make_proc(returncode=1, stdout=b"", stderr=b"API error again")
    gemini_proc   = make_proc(returncode=0, stdout=b"gemini fallback\n")

    side_effects = [claude_proc_1, claude_proc_2, gemini_proc]

    with patch("asyncio.create_subprocess_exec", side_effect=side_effects) as mock_exec:
        result = await call_llm("test prompt")

    # Successful fallback after claude api_error: result reflects gemini success.
    assert result.error is None
    assert result.model_used == "gemini"
    assert result.text == "gemini fallback"
    # 3 subprocess calls: claude attempt 1, claude retry, gemini
    assert mock_exec.call_count == 3


# ---------------------------------------------------------------------------
# Test 4 — Timeout → kill() called, error='timeout'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_kills_process():
    proc = MagicMock()
    proc.returncode = None
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    proc.kill = MagicMock()
    proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await call_llm("test prompt", timeout=1)

    assert result.error == "timeout"
    assert result.text == ""
    proc.kill.assert_called_once()
    proc.wait.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 5 — Session-level cache: after cli_not_found, next call skips claude
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_cache_skips_unavailable_claude():
    # Mark claude unavailable (simulating a previous session finding)
    _cli_available["claude"] = False

    gemini_proc = make_proc(returncode=0, stdout=b"direct gemini\n")

    with patch("asyncio.create_subprocess_exec", return_value=gemini_proc) as mock_exec:
        result = await call_llm("test prompt")

    # Only gemini should be called — claude must NOT be attempted
    mock_exec.assert_called_once()
    args, _ = mock_exec.call_args
    # First positional arg is the executable name
    assert "gemini" in args[0]

    assert result.model_used == "gemini"


# ---------------------------------------------------------------------------
# Test 6 — Prompt passed via stdin, NOT as CLI arg
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_passed_via_stdin():
    prompt_text = "my secret prompt"
    proc = make_proc(returncode=0, stdout=b"response\n")

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        await call_llm(prompt_text)

    # communicate must have been called with input=prompt.encode()
    proc.communicate.assert_called_once_with(input=prompt_text.encode())

    # The prompt must NOT appear in the CLI arguments
    args, kwargs = mock_exec.call_args
    all_args = list(args) + list(kwargs.get("args", []))
    assert prompt_text not in all_args


# ---------------------------------------------------------------------------
# Test 7 — FileNotFoundError treated same as returncode 127
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_not_found_error_treated_as_cli_not_found():
    gemini_proc = make_proc(returncode=0, stdout=b"gemini ok\n")

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=[FileNotFoundError("claude not found"), gemini_proc],
    ) as mock_exec:
        result = await call_llm("test prompt")

    assert _cli_available["claude"] is False
    # Successful gemini fallback: error=None, text propagated.
    assert result.error is None
    assert result.model_used == "gemini"
    assert result.text == "gemini ok"
    assert mock_exec.call_count == 2


# ---------------------------------------------------------------------------
# Test 8 — Empty stdout treated as bad_output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_output_returns_bad_output():
    proc = make_proc(returncode=0, stdout=b"   \n  ")

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await call_llm("test prompt")

    assert result.error == "bad_output"
    assert result.text == ""


# ---------------------------------------------------------------------------
# Test 9 — Both CLIs unavailable → error='cli_not_found', model_used='gemini'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_both_cli_unavailable():
    llm_module._cli_available["claude"] = False
    llm_module._cli_available["gemini"] = False
    result = await call_llm("test")
    assert result.error == "cli_not_found"
    assert result.model_used == "gemini"
    assert result.text == ""
