#!/usr/bin/env python
"""
First-run setup wizard for FeedsAI Starter.

Run once after cloning:

    python scripts/init.py

What it does:
  1. Confirms `claude` CLI is on PATH.
  2. Copies profile.md.example -> profile.md (skips if profile.md exists).
  3. Copies sources.yaml.example -> sources.yaml (skips if sources.yaml exists).
  4. Offers to open profile.md in $EDITOR (or %EDITOR%, or 'notepad' on Windows).
  5. Runs `uv sync` to install dependencies.
  6. Runs scripts/healthcheck.py to verify everything is wired up.

Exits 0 on success, 1 on any setup failure. Re-runnable: skips files that
already exist instead of overwriting.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def info(msg: str) -> None:
    print(f"  {msg}")


def step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def fail(msg: str) -> "None":
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def confirm(prompt: str, default_yes: bool = True) -> bool:
    suffix = " [Y/n] " if default_yes else " [y/N] "
    try:
        reply = input(prompt + suffix).strip().lower()
    except EOFError:
        return default_yes
    if not reply:
        return default_yes
    return reply in {"y", "yes"}


def check_claude_cli() -> None:
    if shutil.which("claude"):
        info("Found `claude` on PATH.")
        return
    print(
        "\n`claude` CLI not found on PATH.\n"
        "  Install: https://docs.claude.com/en/docs/agents-and-tools/claude-code/overview\n"
        "  After install, run `claude` once to authenticate.\n"
        "  Then re-run this script."
    )
    sys.exit(1)


def copy_example(src_name: str, dst_name: str) -> None:
    src = ROOT / src_name
    dst = ROOT / dst_name
    if dst.exists():
        info(f"{dst_name} already exists — skipping copy.")
        return
    if not src.exists():
        fail(f"{src_name} not found at {src}. Did you clone the template?")
    shutil.copyfile(src, dst)
    info(f"Copied {src_name} -> {dst_name}")


def open_in_editor(path: Path) -> None:
    editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "vi")
    if not confirm(f"Open {path.name} in {editor} now?"):
        info("Skipping editor. Open it whenever you like.")
        return
    try:
        subprocess.run([editor, str(path)], check=False)
    except FileNotFoundError:
        info(f"Could not launch {editor}. Open {path} by hand.")


def run_uv_sync() -> None:
    if not shutil.which("uv"):
        info("`uv` not found. Skipping dependency sync.")
        info("Install uv: https://docs.astral.sh/uv/getting-started/installation/")
        info("Then run `uv sync` yourself.")
        return
    info("Running `uv sync` ...")
    result = subprocess.run(["uv", "sync"], cwd=ROOT)
    if result.returncode != 0:
        fail("`uv sync` failed. Fix the error above and re-run.")


def run_healthcheck() -> None:
    healthcheck = ROOT / "scripts" / "healthcheck.py"
    if not healthcheck.exists():
        info("healthcheck.py missing — skipping.")
        return
    info("Running scripts/healthcheck.py ...")
    result = subprocess.run([sys.executable, str(healthcheck)], cwd=ROOT)
    if result.returncode != 0:
        print(
            "\nHealthcheck failed. Most common causes:\n"
            "  - profile.md is still the default template (edit it).\n"
            "  - claude CLI not authenticated (run `claude` once interactively).\n"
            "  - Network blocking RSS fetches.\n"
        )
        sys.exit(1)


def main() -> None:
    steps_total = 5
    print("FeedsAI Starter — first-run setup")
    print("=================================")

    step(1, steps_total, "Check claude CLI")
    check_claude_cli()

    step(2, steps_total, "Set up profile.md")
    copy_example("profile.md.example", "profile.md")
    open_in_editor(ROOT / "profile.md")

    step(3, steps_total, "Set up sources.yaml")
    copy_example("sources.yaml.example", "sources.yaml")

    step(4, steps_total, "Install dependencies")
    run_uv_sync()

    step(5, steps_total, "Healthcheck")
    run_healthcheck()

    print(
        "\nReady. Next steps:\n"
        "  python scripts/fetch.py --verbose       # first feed pull + ranking\n"
        "  .\\scripts\\run_server.ps1 -Detach        # serve digest at http://localhost:8000\n"
    )


if __name__ == "__main__":
    main()
