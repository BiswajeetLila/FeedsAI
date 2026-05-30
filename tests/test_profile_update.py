from app.profile_update import MIN_SIGNALS_FOR_UPDATE, _summarize_learning_patterns


def test_profile_update_threshold_allows_early_learning():
    assert MIN_SIGNALS_FOR_UPDATE == 8


def test_summarize_learning_patterns_groups_topics_and_sources():
    scored_items = [
        {"topic": "ai", "source_title": "Source A", "score": 2.0},
        {"topic": "ai", "source_title": "Source B", "score": 1.5},
        {"topic": "robotics", "source_title": "Source A", "score": 3.0},
    ]

    text = _summarize_learning_patterns(scored_items)

    assert "Top topics:" in text
    assert "- robotics: 3.00 engagement across 1 items" in text
    assert "- ai: 3.50 engagement across 2 items" in text
    assert "- Source A: 5.00 engagement across 2 items" in text
