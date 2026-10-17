from datetime import date
import pytest
from services.ai import analyst


@pytest.mark.asyncio
async def test_latest_multi_metric_comparison_resolves_previous_month(monkeypatch):
    calls = []

    async def aggregate(conn, args, period=None, provider=None):
        calls.append((args.metric, period))
        values = {
            "attendances": (2444743, 2342959),
            "four_hour_pct": (74.36331753480836, 75.04151801205228),
        }
        return {
            "value": values[args.metric][period is not None],
            "unit": "%" if args.metric == "four_hour_pct" else "count",
            "reporting_period": date(2026, 8 if period else 9, 1),
        }

    monkeypatch.setattr(analyst, "aggregate", aggregate)
    result = await analyst.compare_aggregate_periods(
        None, analyst.Args(metrics=["attendances", "four_hour_pct"])
    )
    counts, rates = result["comparisons"]
    assert counts["absolute_change"] == 101784
    assert counts["percentage_change"] == pytest.approx(4.344250155465802)
    assert rates["absolute_change"] == pytest.approx(-0.6782004772439186)
    assert rates["change_unit"] == "percentage points"
    assert calls == [
        ("attendances", None),
        ("attendances", "2026-08"),
        ("four_hour_pct", None),
        ("four_hour_pct", "2026-08"),
    ]


@pytest.mark.asyncio
async def test_comparison_preserves_missingness_and_zero_denominators(monkeypatch):
    async def aggregate(conn, args, period=None, provider=None):
        return {
            "value": None if period is None else 0,
            "unit": "count",
            "reporting_period": date(2026, 1, 1),
        }

    monkeypatch.setattr(analyst, "aggregate", aggregate)
    result = await analyst.compare_aggregate_periods(None, analyst.Args())
    assert result["absolute_change"] is None
    assert result["percentage_change"] is None
