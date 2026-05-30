import time

import pytest

from app.config import HNSource
from app.fetch_engine import FetchEngine
from app.ingest.rss import RawItem


def _raw(n: int) -> RawItem:
    return RawItem(
        url=f"https://example.com/{n}",
        canonical_url=f"https://example.com/{n}",
        title=f"Item {n}",
        author=None,
        published_at=None,
        excerpt=None,
        source_title=None,
    )


@pytest.mark.asyncio
async def test_fetch_engine_runs_blocking_adapters_concurrently():
    sources = [HNSource(kind="hn", title=f"HN {n}") for n in range(3)]

    def fetch_one(source):
        time.sleep(0.1)
        return [_raw(int(source.title.split()[-1]))]

    started = time.monotonic()
    results = await FetchEngine(fetch_one=fetch_one, max_concurrency=3).fetch_many(sources)
    elapsed = time.monotonic() - started

    assert elapsed < 0.25
    assert [result.items[0].title for result in results] == ["Item 0", "Item 1", "Item 2"]
    assert all(result.error is None for result in results)


@pytest.mark.asyncio
async def test_fetch_engine_captures_adapter_errors():
    source = HNSource(kind="hn", title="HN")

    def fetch_one(_source):
        raise RuntimeError("network down")

    results = await FetchEngine(fetch_one=fetch_one).fetch_many([source])

    assert len(results) == 1
    assert results[0].items == []
    assert isinstance(results[0].error, RuntimeError)
