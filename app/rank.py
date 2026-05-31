"""
Batch LLM scoring for FeedsAI.

Ranks items in batches using call_llm(), parses JSON scores, and stores
ranking results in SQLite.
"""
import json
import logging
import sqlite3
from dataclasses import dataclass

from app.db import Item, update_item_rank_failure, update_item_score
from app.llm import LLMResult, call_llm
from app.paths import resource_path

logger = logging.getLogger(__name__)

PROMPT_VERSION = "rank_v1"
_PROMPT_TEMPLATE = resource_path("prompts", "rank_v1.txt").read_text(encoding="utf-8")


@dataclass(frozen=True)
class RankingResult:
    item_id: int
    score: float
    rationale: str = ""
    topic: str | None = None
    status: str = "ranked"
    error: str | None = None


VALID_TOPICS = frozenset({
    "space", "robotics", "ai", "science", "design",
    "scifi", "rationalism", "engineering", "india", "other",
})


async def rank_items(
    items: list[Item],
    profile_md: str,
    conn: sqlite3.Connection,
    max_batch: int = 50,
) -> dict[int, float]:
    """
    Rank unranked items in batches. Returns {item_id: score}.
    Ranked and failed states are persisted so failed/low-score items do not
    get sent to the LLM again on every fetch.
    """
    unranked = [
        item for item in items
        if item.ranking_status == "unranked" and item.score <= 0.0
    ]

    if not unranked:
        logger.debug("rank_items: all items already ranked, nothing to do")
        return {}

    all_results: dict[int, RankingResult] = {}

    for batch_start in range(0, len(unranked), max_batch):
        batch = unranked[batch_start : batch_start + max_batch]
        batch_results = await _rank_batch(batch, profile_md, max_batch=len(batch))
        all_results.update(batch_results)

    for item_id, result in all_results.items():
        if result.status == "ranked":
            update_item_score(
                conn,
                item_id,
                result.score,
                result.rationale,
                PROMPT_VERSION,
                topic=result.topic,
            )
        else:
            update_item_rank_failure(
                conn,
                item_id,
                result.error or "unknown",
                PROMPT_VERSION,
            )

    return {item_id: result.score for item_id, result in all_results.items()}


def _failed_results(batch: list[Item], error: str) -> dict[int, RankingResult]:
    return {
        item.id: RankingResult(
            item_id=item.id,
            score=0.0,
            status="failed",
            error=error,
        )
        for item in batch
    }


async def _rank_batch(
    batch: list[Item],
    profile_md: str,
    max_batch: int = 50,
) -> dict[int, RankingResult]:
    """
    Rank a single batch. Returns {item_id: RankingResult}.
    On JSON parse failure: halve batch, retry recursively down to batch_size=1.
    On LLM error: return failed results so caller can persist non-retry state.
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

    if result.error is not None:
        logger.warning(
            "_rank_batch: LLM returned error=%r for batch of %d items; marking failed",
            result.error,
            len(batch),
        )
        return _failed_results(batch, result.error)

    raw_text = result.text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    try:
        data = json.loads(raw_text)
        rankings = data["rankings"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        if max_batch <= 1:
            logger.warning(
                "_rank_batch: JSON parse failed at batch_size=1 for item ids=%s; marking failed. Error: %s",
                [item.id for item in batch],
                exc,
            )
            return _failed_results(batch, "bad_json")

        new_max = max(1, max_batch // 2)
        logger.warning(
            "_rank_batch: JSON parse failed (batch_size=%d); halving to %d. Error: %s",
            max_batch,
            new_max,
            exc,
        )

        results: dict[int, RankingResult] = {}
        for sub_start in range(0, len(batch), new_max):
            sub_batch = batch[sub_start : sub_start + new_max]
            sub_results = await _rank_batch(sub_batch, profile_md, max_batch=new_max)
            results.update(sub_results)
        return results

    results: dict[int, RankingResult] = {}

    for entry in rankings:
        item_id = entry.get("id")
        if item_id is None:
            continue

        raw_rationale = entry.get("rationale", "")
        raw_topic = entry.get("topic", "")
        topic = raw_topic if raw_topic in VALID_TOPICS else None

        if "score" not in entry:
            logger.warning(
                "_rank_batch: missing 'score' key for item id=%s; marking failed",
                item_id,
            )
            results[item_id] = RankingResult(
                item_id=item_id,
                score=0.0,
                rationale=raw_rationale,
                topic=topic,
                status="failed",
                error="missing_score",
            )
            continue

        try:
            raw_score = float(entry["score"])
        except (TypeError, ValueError):
            logger.warning(
                "_rank_batch: invalid 'score' value for item id=%s; marking failed",
                item_id,
            )
            results[item_id] = RankingResult(
                item_id=item_id,
                score=0.0,
                rationale=raw_rationale,
                topic=topic,
                status="failed",
                error="invalid_score",
            )
            continue

        clamped = max(0.0, min(10.0, raw_score))
        results[item_id] = RankingResult(
            item_id=item_id,
            score=clamped,
            rationale=raw_rationale,
            topic=topic,
        )

    for item in batch:
        if item.id not in results:
            logger.warning(
                "_rank_batch: item id=%d not in LLM response; marking failed",
                item.id,
            )
            results[item.id] = RankingResult(
                item_id=item.id,
                score=0.0,
                status="failed",
                error="missing_item",
            )

    return results
