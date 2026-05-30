"""
Engagement signal vocabulary and scoring.
"""

VALID_EVENTS = frozenset({"viewed", "opened", "linked_out", "liked"})

ENGAGEMENT_WEIGHTS = {
    "viewed": 0.05,
    "opened": 0.4,
    "linked_out": 0.6,
    "liked": 1.5,
}

DWELL_CAP_SECONDS = 120.0


def compute_engagement_score(
    viewed: int,
    opened: int,
    linked_out: int,
    liked: int,
    dwell_seconds: float,
) -> float:
    """Convert engagement events into one profile-learning score."""
    return (
        ENGAGEMENT_WEIGHTS["viewed"] * viewed
        + ENGAGEMENT_WEIGHTS["opened"] * opened
        + ENGAGEMENT_WEIGHTS["linked_out"] * linked_out
        + ENGAGEMENT_WEIGHTS["liked"] * liked
        + min(dwell_seconds / DWELL_CAP_SECONDS, 1.0)
    )
