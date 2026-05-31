"""
app/profile_update.py
Weekly job that analyzes reading behavior and proposes a profile.md update.
"""
import logging
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from app.db import get_db
from app.engagement import compute_engagement_score
from app.llm import call_llm
from app.paths import resolve_user_path
from app.reason_labels import clean_rationale

MIN_SIGNALS_FOR_UPDATE = 8  # skip if fewer than 8 opens/likes in period

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are helping update a personal interest profile used for news ranking.

CURRENT PROFILE:
{current_profile}

ITEMS THE USER ENGAGED WITH MOST (top 10 by engagement):
{liked_items}

ITEMS THE USER IGNORED OR SKIPPED (bottom 10 by engagement):
{disliked_items}

AGGREGATED LEARNING SIGNALS:
{learning_patterns}

Based on this reading behavior, propose an updated profile.md that better reflects the user's actual interests.
Keep the same format as the current profile. Explain the key changes at the end.
Return ONLY the new profile.md content (no JSON, no code blocks).\
"""


def _summarize_learning_patterns(scored_items: list[dict]) -> str:
    topic_totals: dict[str, float] = defaultdict(float)
    topic_counts: dict[str, int] = defaultdict(int)
    source_totals: dict[str, float] = defaultdict(float)
    source_counts: dict[str, int] = defaultdict(int)

    for item in scored_items:
        score = float(item["score"])
        topic = item.get("topic") or "other"
        source = item.get("source_title") or "unknown source"
        topic_totals[topic] += score
        topic_counts[topic] += 1
        source_totals[source] += score
        source_counts[source] += 1

    def _top_lines(label: str, totals: dict[str, float], counts: dict[str, int]) -> list[str]:
        rows = sorted(totals.items(), key=lambda row: row[1], reverse=True)[:5]
        lines = [f"{label}:"]
        if not rows:
            lines.append("- none")
            return lines
        for key, total in rows:
            lines.append(f"- {key}: {total:.2f} engagement across {counts[key]} items")
        return lines

    lines = []
    lines.extend(_top_lines("Top topics", topic_totals, topic_counts))
    lines.extend(_top_lines("Top sources", source_totals, source_counts))
    return "\n".join(lines)


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
    3. If opens + likes < MIN_SIGNALS_FOR_UPDATE: log warning, return False
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
    resolved_profile = resolve_user_path(profile_path)
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
                i.topic,
                i.score AS rank_score,
                i.rank_rationale,
                i.is_liked,
                i.total_dwell_seconds,
                s.title AS source_title,
                COALESCE(SUM(CASE WHEN a.event = 'viewed'     THEN 1 ELSE 0 END), 0) AS viewed_count,
                COALESCE(SUM(CASE WHEN a.event = 'opened'     THEN 1 ELSE 0 END), 0) AS opened_count,
                COALESCE(SUM(CASE WHEN a.event = 'linked_out' THEN 1 ELSE 0 END), 0) AS linked_out_count,
                COALESCE(SUM(CASE WHEN a.event = 'liked'      THEN 1 ELSE 0 END), 0) AS liked_count
            FROM items i
            LEFT JOIN sources s ON i.source_id = s.id
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
    total_liked = 0
    for row in rows:
        viewed = int(row["viewed_count"])
        opened = int(row["opened_count"])
        linked_out = int(row["linked_out_count"])
        liked = max(int(row["liked_count"]), int(row["is_liked"] or 0))
        dwell = float(row["total_dwell_seconds"] or 0.0)

        total_opened += opened
        total_liked += liked
        score = compute_engagement_score(viewed, opened, linked_out, liked, dwell)
        scored_items.append({
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "excerpt": row["excerpt"] or "",
            "topic": row["topic"] or "other",
            "source_title": row["source_title"] or "unknown source",
            "rank_score": float(row["rank_score"] or 0.0),
            "rank_rationale": clean_rationale(row["rank_rationale"]),
            "liked": liked > 0,
            "score": score,
        })

    # --- Check minimum activity threshold ---
    total_signals = total_opened + total_liked
    if total_signals < MIN_SIGNALS_FOR_UPDATE:
        logger.warning(
            "profile_update: only %d opens/likes in last %d days (min %d required); skipping",
            total_signals,
            days,
            MIN_SIGNALS_FOR_UPDATE,
        )
        return False

    # --- Sort and pick top/bottom 10 ---
    scored_items.sort(key=lambda x: x["score"], reverse=True)
    liked_items = scored_items[:10]
    disliked_items = scored_items[-10:]

    def _format_items(items: list[dict]) -> str:
        lines = []
        for item in items:
            excerpt_snippet = item["excerpt"][:100].strip() if item["excerpt"] else ""
            rationale = item["rank_rationale"][:100].strip() if item["rank_rationale"] else ""
            lines.append(
                f"- [{item['title']}]({item['url']})"
                + f"\n  topic={item['topic']} source={item['source_title']} rank={item['rank_score']:.1f}"
                + (f"\n  {excerpt_snippet}" if excerpt_snippet else "")
                + (f"\n  ranking rationale: {rationale}" if rationale else "")
                + ("\n  liked" if item.get("liked") else "")
                + f"  (score: {item['score']:.2f})"
            )
        return "\n".join(lines) if lines else "(none)"

    liked_str = _format_items(liked_items)
    disliked_str = _format_items(disliked_items)
    learning_patterns = _summarize_learning_patterns(scored_items)

    prompt = _PROMPT_TEMPLATE.format(
        current_profile=current_profile,
        liked_items=liked_str,
        disliked_items=disliked_str,
        learning_patterns=learning_patterns,
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
