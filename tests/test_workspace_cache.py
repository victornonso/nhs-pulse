import pytest
from apps.api import cache


@pytest.mark.asyncio
async def test_publication_cache_isolates_copies_and_invalidates(monkeypatch):
    cache.entries.clear()
    generation = 1
    calls = []

    async def fetch(*args):
        return [{"generation": generation}]

    async def workspace(*args):
        calls.append(1)
        return {"rows": [{"value": generation}]}

    monkeypatch.setattr(cache, "fetch", fetch)
    monkeypatch.setattr(cache, "workspace", workspace)
    first = await cache.published_workspace(None, "analyst", {})
    first["private_history"] = ["visitor A"]
    first["rows"][0]["value"] = 999
    second = await cache.published_workspace(None, "analyst", {})
    assert "private_history" not in second
    assert second["rows"][0]["value"] == 1
    assert len(calls) == 1
    generation = 2
    assert (await cache.published_workspace(None, "analyst", {}))["rows"][0][
        "value"
    ] == 2
    assert len(calls) == 2
    assert not cache.locks


@pytest.mark.asyncio
async def test_failed_query_releases_cache_lock(monkeypatch):
    async def fetch(*args):
        return [{"generation": 123}]

    async def workspace(*args):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(cache, "fetch", fetch)
    monkeypatch.setattr(cache, "workspace", workspace)
    with pytest.raises(RuntimeError):
        await cache.published_workspace(None, "operations", {})
    assert not cache.locks
