from datetime import datetime, date, UTC
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import pandas as pd
import pytest
from pipelines.adapters.nhs import ae, beds, diagnostics, number, total
from pipelines.validation.checks import validate
from pipelines.discovery.sources import allowed_url
from services.forecasting.train import predict, evaluate
from services.ai.analyst import Args, numeric_support

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.parametrize("v", [None, "", "*", "..", "-", "N/A", float("nan")])
def test_missing_is_not_zero(v):
    assert number(v) is None


def test_zero_and_suppression():
    assert number("0") == 0
    assert total([1, None]) is None
    assert total([0, 2]) == 2


def test_official_ae_denominator():
    parsed = ae((FIXTURES / "ae-september-2026.csv").read_bytes(), "September 2026")
    national = next(
        r
        for r in parsed.rows
        if r["grain"] == "national" and r["attendance_type"] == "all"
    )
    assert national["attendances"] == 2444743
    assert national["booked"] == 74952
    assert national["wait_12_plus"] == 50582
    assert (
        round(
            100
            * (national["attendances"] - national["over_four"])
            / national["attendances"],
            2,
        )
        == 74.36
    )
    assert all(c["passed"] for c in validate(parsed) if c["severity"] == "critical")


def test_source_total_case_is_not_a_provider():
    body = (FIXTURES / "ae-september-2026.csv").read_bytes().replace(b"TOTAL", b"Total")
    parsed = ae(body, "September 2026")
    assert len([r for r in parsed.rows if r["grain"] == "national"]) == 4


def test_kh03_quarter_only():
    parsed = beds((FIXTURES / "beds-q1-2026.xlsx").read_bytes(), "Quarter 1 2026-27")
    assert parsed.period == date(2026, 4, 1)
    assert {r["days_in_quarter"] for r in parsed.rows} == {91}
    n = next(
        r for r in parsed.rows if r["grain"] == "national" and r["specialty"] == "Total"
    )
    assert n["available_bed_days"] == pytest.approx(n["available_average"] * 91)
    assert all(
        r["available_average"] is None
        for r in parsed.rows
        if r["specialty"][:3].isdigit()
    )


def test_diagnostics_grains_do_not_double_count():
    parsed = diagnostics(
        (FIXTURES / "diagnostics-august-2026.zip").read_bytes(), "August 2026"
    )
    assert not any(r["test"] == "TOTAL" for r in parsed.rows)
    for grain in ("provider", "commissioner"):
        assert (
            sum(r["waiting_list"] for r in parsed.rows if r["grain"] == grain)
            == 1833070
        )
    assert sum(r["waiting_list"] for r in parsed.exclusions) == 5851
    assert 1833070 - 5851 == 1827219
    assert all(c["passed"] for c in validate(parsed))


def test_official_calendar_exceptions_and_dst():
    entries = json.loads(
        (Path(__file__).parents[2] / "docs/calendar-extract.json").read_text(
            encoding="utf-8"
        )
    )["entries"]
    march = next(
        r for r in entries if r["source"] == "ae" and r["period"] == "2026-03-01"
    )
    assert march["at"].startswith("2026-04-16")
    assert (
        datetime(2026, 7, 1, 9, 30, tzinfo=ZoneInfo("Europe/London"))
        .astimezone(UTC)
        .hour
        == 8
    )
    assert (
        datetime(2026, 12, 1, 9, 30, tzinfo=ZoneInfo("Europe/London"))
        .astimezone(UTC)
        .hour
        == 9
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://www.england.nhs.uk/a.csv",
        "https://www.england.nhs.uk.evil.test/a.csv",
        "file:///a",
        "https://127.0.0.1/a",
    ],
)
def test_download_allowlist(url):
    assert not allowed_url(url)


def test_tool_arguments_block_sql():
    with pytest.raises(Exception):
        Args.model_validate({"sql": "DROP TABLE core.ae_monthly"})
    with pytest.raises(Exception):
        Args.model_validate({"providers": ["X"] * 4})
    assert not numeric_support("There were 999 attendances", [{"value": 20}])
    assert numeric_support("There were 20.00 attendances", [{"value": 20}])


def test_rolling_forecast_uses_past_only():
    values = list(range(100, 136))
    dates = pd.date_range("2023-01-01", periods=36, freq="MS")
    a = evaluate(values, dates)
    modified = values.copy()
    modified[-1] = 999999
    b = evaluate(modified, dates)
    assert [r["predicted"] for r in a] == [r["predicted"] for r in b]
    assert predict(values[:24], 3, "Seasonal naïve").tolist() == [112, 113, 114]
