from services.forecasting.train import comparability_check


def test_recent_abrupt_level_shift_requires_review():
    assert comparability_check([100] * 30 + [180] * 6)["flagged_indices"] == list(
        range(30, 36)
    )


def test_repeated_seasonality_is_comparable():
    assert not comparability_check(([100, 110, 90, 100, 105, 95] * 6))[
        "flagged_indices"
    ]
