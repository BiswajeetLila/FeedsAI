from app.engagement import compute_engagement_score


def test_liked_signal_outweighs_passive_view():
    passive = compute_engagement_score(
        viewed=10,
        opened=0,
        linked_out=0,
        liked=0,
        dwell_seconds=0,
    )
    liked = compute_engagement_score(
        viewed=1,
        opened=0,
        linked_out=0,
        liked=1,
        dwell_seconds=0,
    )

    assert liked > passive


def test_dwell_score_is_capped():
    capped = compute_engagement_score(
        viewed=0,
        opened=0,
        linked_out=0,
        liked=0,
        dwell_seconds=120,
    )
    over_cap = compute_engagement_score(
        viewed=0,
        opened=0,
        linked_out=0,
        liked=0,
        dwell_seconds=240,
    )

    assert over_cap == capped
