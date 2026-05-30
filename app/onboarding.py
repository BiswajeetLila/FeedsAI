"""
First-run setup helpers for FeedsAI.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).parent.parent
PROFILE_PATH = _PROJECT_ROOT / "profile.md"
SOURCES_PATH = _PROJECT_ROOT / "sources.yaml"


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def setup_required() -> bool:
    if not PROFILE_PATH.exists() or not SOURCES_PATH.exists():
        return True
    try:
        profile = PROFILE_PATH.read_text(encoding="utf-8")
    except Exception:
        return True
    return "[Your Name]" in profile or "[Topic A" in profile


def build_profile(
    reader_name: str,
    archetype: str,
    top_interests: str,
    secondary_interests: str,
    avoid_topics: str,
    region: str,
) -> str:
    name = reader_name.strip() or "Reader"
    archetype = archetype.strip() or "Curious technical reader."
    top = _split_lines(top_interests)
    secondary = _split_lines(secondary_interests)
    avoid = _split_lines(avoid_topics)
    region_name = region.strip()

    def bullets(items: list[str], fallback: str) -> str:
        values = items or [fallback]
        return "\n".join(f"- {item}" for item in values)

    region_section = ""
    if region_name:
        region_section = f"""
---

# SECTION 2: {region_name} Bonus (+1.5 to local content)

- Prefer stories with local ecosystem, policy, research, companies, or culture context.
- Boost items where {region_name} changes the practical relevance of the story.
"""

    return f"""# Interest Profile - {name}

Archetype: {archetype}
Core tension: Rank concrete, evidence-backed items above hype, generic summaries, or press rewrites.

---

# SECTION 1: Global Content

## Tier 1: Score 8-10

{bullets(top, "Deep technical explainers, research, tools, and launches with practical impact.")}

## Tier 2: Score 5-7

{bullets(secondary, "Adjacent topics worth skimming when the digest is otherwise quiet.")}

## Tier 3: Score 0-4

{bullets(avoid, "Clickbait, generic marketing, shallow drama, and low-signal commentary.")}
{region_section}
---

# Notes for the ranker

- Score against the closest tier.
- Prefer specificity, novelty, and practical consequences.
- Penalize hype without evidence.
"""


def build_sources(
    include_hn: bool,
    include_simon: bool,
    include_quanta: bool,
    arxiv_queries: str,
    rss_urls: str,
    github_repos: str,
) -> str:
    sources: list[dict] = []

    if include_hn:
        sources.append({"kind": "hn", "filter": "front_page", "title": "Hacker News"})
    if include_simon:
        sources.append({
            "kind": "rss",
            "url": "https://simonwillison.net/atom/everything/",
            "title": "Simon Willison",
        })
    if include_quanta:
        sources.append({
            "kind": "rss",
            "url": "https://www.quantamagazine.org/feed/",
            "title": "Quanta Magazine",
        })

    for query in _split_lines(arxiv_queries):
        sources.append({"kind": "arxiv", "query": query, "title": f"arXiv {query}"})

    for url in _split_lines(rss_urls):
        sources.append({"kind": "rss", "url": url})

    for repo in _split_lines(github_repos):
        sources.append({"kind": "github_releases", "repo": repo})

    if not sources:
        sources.append({"kind": "hn", "filter": "front_page", "title": "Hacker News"})

    return yaml.safe_dump(
        {"schema_version": 1, "sources": sources},
        sort_keys=False,
        allow_unicode=True,
    )


def write_setup(profile_md: str, sources_yaml: str) -> None:
    PROFILE_PATH.write_text(profile_md, encoding="utf-8")
    SOURCES_PATH.write_text(sources_yaml, encoding="utf-8")
