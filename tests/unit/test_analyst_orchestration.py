from contextlib import asynccontextmanager
from uuid import uuid4
import httpx
import pytest
from services.ai import analyst


@pytest.mark.asyncio
async def test_repeated_provider_lookups_reuse_evidence_without_exhausting_budget(
    monkeypatch,
):
    class Connection:
        async def execute(self, *args, **kwargs):
            pass

    @asynccontextmanager
    async def session():
        yield Connection()

    async def quota(*args):
        return [{"personal": 0, "global": 0, "minute_count": 0}]

    lookups = []

    async def tool(name, args):
        lookups.append(name)
        return {"value": 20}

    class Provider:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            self.calls += 1
            message = {"role": "assistant", "content": "20 attendances."}
            if self.calls == 1:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call{i}",
                            "type": "function",
                            "function": {"name": "query_aggregate", "arguments": "{}"},
                        }
                        for i in range(9)
                    ],
                }
            return httpx.Response(
                200,
                json={"choices": [{"message": message}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(analyst, "read_session", session)
    monkeypatch.setattr(analyst, "fetch", quota)
    monkeypatch.setattr(analyst, "tool", tool)
    monkeypatch.setattr(analyst.httpx, "AsyncClient", Provider)
    monkeypatch.setattr(analyst.settings, "llm_api_key", "unit-test-key")
    result = await analyst.investigate(str(uuid4()), "Show attendance.")
    assert lookups == ["query_aggregate"]
    assert len(result["evidence"]) == 1
    assert result["answer"] == "20 attendances."
