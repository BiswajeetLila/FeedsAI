"""
app/ingest/__init__.py
Dispatch layer: routes source configs to the correct fetcher.
"""
from app.config import ArxivSource, GithubReleasesSource, HNSource, RSSSource, SourceConfig
from app.ingest.arxiv import fetch_arxiv
from app.ingest.github import fetch_github_releases
from app.ingest.hn import fetch_hn
from app.ingest.rss import RawItem, fetch_rss


def fetch_source(source: SourceConfig) -> list[RawItem]:
    """Dispatch to correct fetcher by source kind."""
    if isinstance(source, RSSSource):
        return fetch_rss(str(source.url), source.title)
    elif isinstance(source, HNSource):
        return fetch_hn(feed_filter=source.filter)  # HNSource.filter = "front_page"
    elif isinstance(source, ArxivSource):
        return fetch_arxiv(source.query)
    elif isinstance(source, GithubReleasesSource):
        return fetch_github_releases(source.repo)
    else:
        raise ValueError(f"Unknown source kind: {type(source)}")
