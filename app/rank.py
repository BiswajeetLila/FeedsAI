"""
Batch LLM scoring for FeedsAI.

Ranks items in batches using call_llm(), parses JSON scores,
and stores results via update_item_score().
"""
import json
import logging
import sqlite3
from pathlib import Path

from app.llm import call_llm, LLMResult
from app.db import Item, update_item_score

logger = logging.getLogger(__name__)

PROMPT_VERSION = "rank_v1"
_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "rank_v1.txt").read_text()


async def rank_items(
    items: list[Item],
    profile_md: str,
    conn: sqlite3.Connection,
    max_batch: int = 50,
) -> dict[int, float]:
    """
    Rank items in batches. Returns dict of {item_id: score}.
    Stores scores in DB via update_item_score.
    Items with score > 0.0 already are considered "ranked" and are skipped.
    """
    # Filter out already-ranked items
    unranked = [item for item in items if item.score <= 0.0]

    if not unranked:
        logger.debug("rank_items: all items already ranked, nothing to do")
        return {}

    all_scores: dict[int, float] = {}

    # Process in batches
    for batch_start in range(0, len(unranked), max_batch):
        batch = unranked[batch_start : batch_start + max_batch]
        batch_scores = await _rank_batch(batch, profile_md, max_batch=len(batch))
        all_scores.update(batch_scores)

    # Persist to DB — we need rationale from a second pass through the LLM result,
    # so we call update_item_score using data collected in _rank_batch.
    # _rank_batch returns scores; rationale is stored internally.
    # We use a separate internal structure to pass rationale through.
    # Re-run via _rank_batch_with_rationale pattern: store in _rationale_cache.
    for item_id, score in all_scores.items():
        rationale = _rationale_cache.pop(item_id, "")
        topic = _topic_cache.pop(item_id, None)
        update_item_score(conn, item_id, score, rationale, PROMPT_VERSION, topic=topic)

    return all_scores


# Internal caches to pass rationale and topic from _rank_batch to rank_items
_rationale_cache: dict[int, str] = {}
_topic_cache: dict[int, str | None] = {}

VALID_TOPICS = frozenset({
    "space", "robotics", "ai", "science", "design",
    "scifi", "rationalism", "engineering", "india", "other",
})


async def _rank_batch(
    batch: list[Item],
    profile_md: str,
    max_batch: int = 50,
) -> dict[int, float]:
    """
    Rank a single batch. Returns {item_id: score}.
    On JSON parse failure: halve batch, retry recursively down to batch_size=1.
    On LLM error (result.error not None): log warning, return {id: 0.0} for all.
    """
    if not batch:
        return {}

    items_json = json.dumps([
        {
            "id": item.id,
            "title": item.title,
            "excerpt": (item.excerpt or "")[:200],
            "source": item.source_id,
        }
        for item in batch
    ])

    prompt = (
        _PROMPT_TEMPLATE
        .replace("{profile}", profile_md)
        .replace("{items_json}", items_json)
    )

    result: LLMResult = await call_llm(prompt)

    # Handle LLM-level error
    if result.error is not None:
        logger.warning(
            "_rank_batch: LLM returned error=%r for batch of %d items; assigning 0.0",
            result.error,
            len(batch),
        )
        return {item.id: 0.0 for item in batch}

    # Strip markdown code fences if present (Claude often wraps JSON in ```json...```)
    raw_text = result.text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        # Drop opening fence line (```json or ```)
        lines = lines[1:]
        # Drop closing fence line if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    # Parse JSON response
    try:
        data = json.loads(raw_text)
        rankings = data["rankings"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        # JSON parse failure — halve the batch and retry recursively
        if max_batch <= 1:
            logger.warning(
                "_rank_batch: JSON parse failed at batch_size=1 for item ids=%s; assigning 0.0. Error: %s",
                [item.id for item in batch],
                exc,
            )
            return {item.id: 0.0 for item in batch}

        new_max = max(1, max_batch // 2)
        logger.warning(
            "_rank_batch: JSON parse failed (batch_size=%d); halving to %d. Error: %s",
            max_batch,
            new_max,
            exc,
        )

        scores: dict[int, float] = {}
        for sub_start in range(0, len(batch), new_max):
            sub_batch = batch[sub_start : sub_start + new_max]
            sub_scores = await _rank_batch(sub_batch, profile_md, max_batch=new_max)
            scores.update(sub_scores)
        return scores

    # Extract scores from parsed rankings
    scores = {}
    id_to_item = {item.id: item for item in batch}

    for entry in rankings:
        item_id = entry.get("id")
        if item_id is None:
            continue

        raw_rationale = entry.get("rationale", "")
        raw_topic = entry.get("topic", "")
        topic = raw_topic if raw_topic in VALID_TOPICS else None

        if "score" not in entry:
            logger.warning(
                "_rank_batch: missing 'score' key for item id=%s; assigning 0.0",
                item_id,
            )
            scores[item_id] = 0.0
            _rationale_cache[item_id] = raw_rationale
            _topic_cache[item_id] = topic
        else:
            raw_score = float(entry["score"])
            clamped = max(0.0, min(10.0, raw_score))
            scores[item_id] = clamped
            _rationale_cache[item_id] = raw_rationale
            _topic_cache[item_id] = topic

    # Any items in the batch not returned by the LLM get 0.0
    for item in batch:
        if item.id not in scores:
            logger.warning(
                "_rank_batch: item id=%d not in LLM response; assigning 0.0",
                item.id,
            )
            scores[item.id] = 0.0
            _rationale_cache[item.id] = ""
            _topic_cache[item.id] = None

    return scores
