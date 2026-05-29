"""
app/config.py
Configuration models for FeedsAI.

Validates sources.yaml at startup and provides typed access to source configs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator

_PROJECT_ROOT = Path(__file__).parent.parent  # app/ -> project root


class RSSSource(BaseModel):
    """An RSS 2.0 or Atom feed source."""

    kind: Literal["rss"]
    url: HttpUrl  # validates http/https only
    title: str | None = None
    topic: str | None = None


class HNSource(BaseModel):
    """Hacker News front-page source via the official Firebase API."""

    kind: Literal["hn"]
    filter: Literal["front_page"] = "front_page"
    title: str = "Hacker News"
    topic: str | None = None


class ArxivSource(BaseModel):
    """An arXiv search query source (uses the arXiv API query syntax)."""

    kind: Literal["arxiv"]
    query: str
    title: str | None = None
    topic: str | None = None

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("arXiv query must not be empty")
        return v.strip()


class GithubReleasesSource(BaseModel):
    """A GitHub repository releases source ('owner/repo' format)."""

    kind: Literal["github_releases"]
    repo: str  # "owner/repo" format
    title: str | None = None
    topic: str | None = None

    @field_validator("repo")
    @classmethod
    def validate_repo_format(cls, v: str) -> str:
        parts = v.strip().split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"repo must be in 'owner/repo' format, got: {v!r}"
            )
        return v.strip()


# Type alias for any valid source config
SourceConfig = RSSSource | HNSource | ArxivSource | GithubReleasesSource


class SourcesFile(BaseModel):
    """Root model for sources.yaml."""

    schema_version: int = 1
    sources: list[SourceConfig] = Field(min_length=1)

    model_config = {"populate_by_name": True}


def load_sources(path: str | Path = "sources.yaml") -> SourcesFile:
    """Load and validate sources.yaml. Raises ValidationError on bad config."""
    resolved = Path(path) if Path(path).is_absolute() else _PROJECT_ROOT / path
    with open(resolved, encoding="utf-8") as f:
        data = yaml.load(f, Loader=yaml.SafeLoader)
    return SourcesFile.model_validate(data)
