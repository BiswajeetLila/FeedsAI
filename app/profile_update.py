"""
app/profile_update.py
Weekly job that analyzes reading behavior and proposes a profile.md update.
"""
import logging
import subprocess
import sys
import time
from pathlib import Path

from app.db import get_db
from app.llm import call_llm

_PROJECT_ROOT = Path(__file__).parent.parent

ENGAGEMENT_WEIGHTS = {"viewed": 0.1, "opened": 0.4, "linked_out": 0.5}
DWELL_CAP_SECONDS = 120.0
MIN_ITEMS_FOR_UPDATE = 20  # skip if fewer than 20 items were opened in period

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are helping update a personal interest profile used for news ranking.

CURRENT PROFILE:
{current_profile}

ITEMS THE USER ENGAGED WITH MOST (top 10 by engagement):
{liked_items}

ITEMS THE USER IGNORED OR SKIPPED (bottom 10 by engagement):
{disliked_items}

Based on this reading behavior, propose an updated profile.md that better reflects the user's actual interests.
Keep the same format as the current profile. Explain the key changes at the end.
Return ONLY the new profile.md content (no JSON, no code blocks).\
"""


def compute_engagement_score(
    viewed: int,
    opened: int,
    linked_out: int,
    dwell_seconds: float,
) -> float:
    """
    engagement = 0.1*viewed + 0.4*opened + 0.5*linked_out + min(dwell/120, 1.0)
    """
    return (
        ENGAGEMENT_WEIGHTS["viewed"] * viewed
        + ENGAGEMENT_WEIGHTS["opened"] * opened
        + ENGAGEMENT_WEIGHTS["linked_out"] * linked_out
        + min(dwell_seconds / DWELL_CAP_SECONDS, 1.0)
    )


async def propose_profile_update(
    profile_path: str = "profile.md",
    days: int = 7,
    preview: bool = False,
) -> bool:
    """
    Analyze last N days of activity, propose profile.md update.

    Steps:
    1. Load items + activity from last N days from DB
    2. Compute engagement_score per item
    3. If total opened < MIN_ITEMS_FOR_UPDATE: log warning, return False
    4. Sort by engagement: top 10 = "liked", bottom 10 = "disliked"
    5. Build prompt with current profile.md + liked/disliked samples
    6. Call LLM: "propose a revised profile.md"
    7. Write proposed profile to profile_path + ".proposed"
    8. If not preview: run `git diff --no-index profile.md profile.md.proposed` (subprocess)
       Show diff. Prompt user y/N. If y: rename .proposed -> profile.md.
    9. Return True on success
    """
    try:
        return await _propose_profile_update_inner(
            profile_path=profile_path,
            days=days,
            preview=preview,
        )
    except Exception as e:
        logger.error("propose_profile_update failed: %s", e, exc_info=True)
        return False


async def _propose_profile_update_inner(
    profile_path: str = "profile.md",
    days: int = 7,
    preview: bool = False,
) -> bool:
    # --- Resolve profile path ---
    resolved_profile = (
        Path(profile_path) if Path(profile_path).is_absolute()
        else _PROJECT_ROOT / profile_path
    )
    proposed_path = Path(str(resolved_profile) + ".proposed")

    # --- Load current profile ---
    try:
        current_profile = resolved_profile.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("profile_update: profile.md not found at %s; using empty", resolved_profile)
        current_profile = ""

    # --- Query DB for items + activity in last N days ---
    cutoff = int(time.time()) - days * 86400

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                i.id,
                i.title,
                i.url,
                i.excerpt,
                i.total_dwell_seconds,
                COALESCE(SUM(CASE WHEN a.event = 'viewed'     THEN 1 ELSE 0 END), 0) AS viewed_count,
                COALESCE(SUM(CASE WHEN a.event = 'opened'     THEN 1 ELSE 0 END), 0) AS opened_count,
                COALESCE(SUM(CASE WHEN a.event = 'linked_out' THEN 1 ELSE 0 END), 0) AS linked_out_count
            FROM items i
            LEFT JOIN activity a ON a.item_id = i.id AND a.ts >= ?
            WHERE i.fetched_at >= ?
            GROUP BY i.id
            """,
            (cutoff, cutoff),
        ).fetchall()

    if not rows:
        logger.warning("profile_update: no items found in last %d days; skipping", days)
        return False

    # --- Compute engagement score per item ---
    scored_items = []
    total_opened = 0
    for row in rows:
        viewed = int(row["viewed_count"])
        opened = int(row["opened_count"])
        linked_out = int(row["linked_out_count"])
        dwell = float(row["total_dwell_seconds"] or 0.0)

        total_opened += opened
        score = compute_engagement_score(viewed, opened, linked_out, dwell)
        scored_items.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "excerpt": row["excerpt"] or "",
            "score": score,
        })

    # --- Check minimum activity threshold ---
    if total_opened < MIN_ITEMS_FOR_UPDATE:
        logger.warning(
            "profile_update: only %d items opened in last %d days (min %d required); skipping",
            total_opened,
            days,
            MIN_ITEMS_FOR_UPDATE,
        )
        return False

    # --- Sort and pick top/bottom 10 ---
    scored_items.sort(key=lambda x: x["score"], reverse=True)
    liked_items = scored_items[:10]
    disliked_items = scored_items[-10:]

    def _format_items(items: list[dict]) -> str:
        lines = []
        for item in items:
            excerpt_snippet = item["excerpt"][:120].strip() if item["excerpt"] else ""
            lines.append(
                f"- [{item['title']}]({item['url']})"
                + (f"\n  {excerpt_snippet}" if excerpt_snippet else "")
                + f"  (score: {item['score']:.2f})"
            )
        return "\n".join(lines) if lines else "(none)"

    liked_str = _format_items(liked_items)
    disliked_str = _format_items(disliked_items)

    prompt = _PROMPT_TEMPLATE.format(
        current_profile=current_profile,
        liked_items=liked_str,
        disliked_items=disliked_str,
    )

    # --- Call LLM ---
    logger.info("profile_update: calling LLM to propose profile update...")
    result = await call_llm(prompt, timeout=120)

    if result.error is not None or not result.text:
        logger.error(
            "profile_update: LLM call failed (error=%s model=%s); aborting",
            result.error,
            result.model_used,
        )
        return False

    proposed_content = result.text

    # --- Write .proposed file ---
    proposed_path.write_text(proposed_content, encoding="utf-8")
    logger.info("profile_update: proposed profile written to %s", proposed_path)

    if preview:
        # Just show the proposed content, no prompting
        print(f"\n--- Proposed {resolved_profile.name} ---")
        print(proposed_content)
        print(f"--- End proposed {resolved_profile.name} ---\n")
        print(f"Proposed file saved to: {proposed_path}")
        return True

    # --- Show diff and prompt user ---
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--no-index",
             str(resolved_profile), str(proposed_path)],
            capture_output=True,
            text=True,
        )
        diff_output = diff_result.stdout or diff_result.stderr
        if diff_output.strip():
            print(diff_output)
        else:
            print("(No differences — proposed profile is identical to current)")
    except Exception as exc:
        logger.warning("profile_update: could not run git diff: %s", exc)
        print(f"\n--- Proposed profile saved to: {proposed_path} ---")

    # --- Prompt user ---
    try:
        answer = input("Apply proposed profile? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer == "y":
        proposed_path.replace(resolved_profile)
        logger.info("profile_update: profile.md updated from proposed")
        print("profile.md updated.")
    else:
        logger.info("profile_update: user declined; proposed file kept at %s", proposed_path)
        print(f"Not applied. Proposed file kept at: {proposed_path}")

    return True
