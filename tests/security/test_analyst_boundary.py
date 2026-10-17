import pytest
from pydantic import ValidationError
from services.ai.analyst import Args, numeric_support, tool


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "select * from ai.conversation"},
        {"metric": "password"},
        {"period": "2026-10 OR 1=1"},
        {"provider": "R0A;DROP"},
        {"horizon": 999},
    ],
)
def test_tool_injection_rejected(arguments):
    with pytest.raises(ValidationError):
        Args.model_validate(arguments)


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected_before_database_access():
    with pytest.raises(ValueError):
        await tool("execute_sql", {"sql": "select 1"})


def test_date_precision_and_numeric_grounding():
    assert numeric_support(
        "Published 8 October 2026, with 2,444,743 attendances.",
        [{"date": "2026-10-08", "value": 2444743}],
    )
    assert not numeric_support(
        "There were 9,999,999 attendances.", [{"value": 2444743}]
    )
