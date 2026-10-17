import pytest
from services.ai.analyst import numeric_support


@pytest.mark.parametrize("sign", ["-", "\u2212"])
def test_negative_rate_change_keeps_its_sign_when_rounded(sign):
    evidence = {
        "absolute_change": -0.6782004772439186,
        "percentage_change": -0.9037670015350623,
    }
    assert numeric_support(
        f"Change: {sign}0.68 percentage points ({sign}0.90%).", evidence
    )
    assert not numeric_support("Change: +0.68 percentage points (+0.90%).", evidence)


def test_monthly_comparison_with_dates_counts_rates_and_citations():
    identifier = "bb3a56b9-2a2c-4120-934a-f9944babcf77"
    evidence = {
        "id": identifier,
        "dates": ["2026-09-01", "2026-08-01"],
        "attendances": [2444743, 2342959],
        "attendance_change": 101784,
        "attendance_percentage_change": 4.344250155465802,
        "rates": [74.36331753480836, 75.04151801205228],
        "rate_change": -0.6782004772439186,
    }
    answer = f"September 2026: 2,444,743 vs August 2026: 2,342,959; +101,784 (+4.34%). Four-hour performance: 74.36% vs 75.04%, down -0.68 percentage points. Evidence `{identifier}`."
    assert numeric_support(answer, evidence)
    assert not numeric_support(answer.replace("101,784", "999,999"), evidence)


def test_technical_identifiers_do_not_authorize_measurements():
    identifier = "bb3a56b9-2a2c-4120-934a-f9944babcf77"
    evidence = {
        "id": identifier,
        "official_url": "https://example.org/releases/934/file.csv",
        "value": 20,
    }
    assert not numeric_support("There were 934 attendances.", evidence)
    assert not numeric_support("There were 4120 attendances.", evidence)
    assert not numeric_support(
        "Evidence `00000000-0000-0000-0000-000000000000` reports 20 attendances.",
        evidence,
    )


def test_iso_date_separators_are_not_negative_quantities():
    assert numeric_support(
        "Reporting period 2026-09-01; change -0.68.",
        {"period": "2026-09-01", "change": -0.6782},
    )


def test_availability_flags_are_not_measurements():
    assert numeric_support("The forecast is unavailable.", {"available": False})
    assert not numeric_support("There were 1 attendances.", {"available": True})


@pytest.mark.parametrize(
    "answer",
    [
        "The rate fell by 0.68 percentage points.",
        "The rate was down **0.68** percentage points.",
        "A 0.68 percentage-point decrease.",
        "The rate declined 0.68 points.",
    ],
)
def test_negative_changes_can_be_expressed_in_words(answer):
    assert numeric_support(answer, {"change": -0.6782})
    assert not numeric_support(answer.replace("0.68", "0.99"), {"change": -0.6782})


def test_grounding_diagnostics_identify_unsupported_values():
    diagnostics = {}
    assert not numeric_support("Change +0.68.", {"change": -0.6782}, diagnostics)
    assert diagnostics["unsupported_numbers"] == ["+0.68"]
