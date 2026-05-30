"""
Bounded async fetch engine for source adapters.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from app.config import SourceConfig
from app.ingest import fetch_source
from app.ingest.rss import RawItem

FetchOne = Callable[[SourceConfig], list[RawItem]]


@dataclass(frozen=True)
class SourceFetchResult:
    source: SourceConfig
    items: list[RawItem]
    error: Exception | None = None


class FetchEngine:
    """Run blocking source adapters without blocking the event loop."""

    def __init__(
        self,
        fetch_one: FetchOne = fetch_source,
        max_concurrency: int = 4,
        timeout_seconds: int = 30,
    ) -> None:
        self.fetch_one = fetch_one
        self.max_concurrency = max(1, max_concurrency)
        self.timeout_seconds = timeout_seconds

    async def fetch_many(self, sources: list[SourceConfig]) -> list[SourceFetchResult]:
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _one(source: SourceConfig) -> SourceFetchResult:
            async with sem:
                try:
                    items = await asyncio.wait_for(
                        asyncio.to_thread(self.fetch_one, source),
                        timeout=self.timeout_seconds,
                    )
                    return SourceFetchResult(source=source, items=items)
                except Exception as exc:
                    return SourceFetchResult(source=source, items=[], error=exc)

        return await asyncio.gather(*[_one(source) for source in sources])
