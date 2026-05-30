"""
Cheap content-quality signals for digest shaping.

These rules are deliberately conservative. They only hide low-score items by
default and never affect saved items.
"""
import re
import time

from app.db import Item

_CLICKBAIT_RE = re.compile(
    r"\b("
    r"shocking|mind[- ]?blowing|you won't believe|what happened next|"
    r"ultimate guide|everything you need to know|top \d+|secret to"
    r")\b",
    re.IGNORECASE,
)
_PROMO_RE = re.compile(
    r"\b(sponsored|partner content|coupon|discount|limited time|deal of the day)\b",
    re.IGNORECASE,
)


def low_signal_reasons(item: Item) -> list[str]:
    text = f"{item.title} {item.excerpt or ''}"
    reasons: list[str] = []

    if _CLICKBAIT_RE.search(text):
        reasons.append("clickbait wording")
    if _PROMO_RE.search(text):
        reasons.append("promo wording")
    if len((item.excerpt or "").strip()) < 60:
        reasons.append("thin excerpt")
    if item.score < 3.0:
        reasons.append("very low fit")

    return reasons


def is_low_signal(item: Item) -> bool:
    if item.is_saved or item.score >= 6.5:
        return False
    reasons = low_signal_reasons(item)
    return bool(reasons) and (item.score < 5.0 or len(reasons) >= 2)


def novelty_label(
    item: Item,
    cluster_size: int | None = None,
    *,
    now: int | None = None,
) -> str:
    if cluster_size and cluster_size > 1:
        return ""
    published_at = item.published_at or item.fetched_at
    current_time = now if now is not None else int(time.time())
    age_seconds = current_time - published_at if published_at else 999999

    if item.score >= 7.0 and age_seconds <= 24 * 3600:
        return "Novel"
    if age_seconds <= 6 * 3600:
        return "Fresh angle"
    return ""
