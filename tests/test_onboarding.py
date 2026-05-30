from app.onboarding import build_profile, build_sources


def test_build_profile_uses_user_interests():
    profile = build_profile(
        reader_name="Ada",
        archetype="AI systems builder",
        top_interests="Robotics\nLLM agents",
        secondary_interests="Design systems",
        avoid_topics="Celebrity news",
        region="India",
    )

    assert "# Interest Profile - Ada" in profile
    assert "- Robotics" in profile
    assert "- LLM agents" in profile
    assert "# SECTION 2: India Bonus" in profile
    assert "Celebrity news" in profile


def test_build_sources_includes_starter_and_custom_sources():
    sources = build_sources(
        include_hn=True,
        include_simon=False,
        include_quanta=False,
        arxiv_queries="cat:cs.AI",
        rss_urls="https://example.com/feed.xml",
        github_repos="owner/repo",
    )

    assert "schema_version: 1" in sources
    assert "kind: hn" in sources
    assert "query: cat:cs.AI" in sources
    assert "url: https://example.com/feed.xml" in sources
    assert "repo: owner/repo" in sources
