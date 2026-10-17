"""Rolling-origin evaluation on published aggregate attendance counts."""

import json
import math
import warnings
import numpy as np
import pandas as pd
from sqlalchemy import text
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from apps.api.database import transaction, records


def predict(values, horizon, candidate):
    values = np.asarray(values, dtype=float)
    if len(values) < 24:
        raise ValueError("At least two complete seasonal cycles are required")
    if candidate == "Seasonal naïve":
        return np.array([values[-12 + i % 12] for i in range(horizon)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ExponentialSmoothing(
            values,
            trend="add",
            damped_trend=True,
            seasonal="add",
            seasonal_periods=12,
            initialization_method="estimated",
        ).fit(optimized=True)
    return np.maximum(fitted.forecast(horizon), 0)


def evaluate(values, dates):
    result = []
    for origin in range(24, len(values)):
        for candidate in ["Seasonal naïve", "Damped seasonal ETS"]:
            estimates = predict(
                values[:origin], min(12, len(values) - origin), candidate
            )
            for h, estimate in enumerate(estimates, 1):
                result.append(
                    {
                        "origin": dates[origin - 1].date(),
                        "period": dates[origin + h - 1].date(),
                        "horizon": h,
                        "actual": float(values[origin + h - 1]),
                        "predicted": float(estimate),
                        "candidate": candidate,
                    }
                )
    return result


def comparability_check(values):
    """Flag abrupt recent seasonal level shifts; this is a screening rule, not proof."""
    values = np.asarray(values, dtype=float)
    seasonal = values[12:] / np.maximum(values[:-12], 1) - 1
    baseline = seasonal[:-6]
    centre = float(np.median(baseline))
    mad = float(np.median(np.abs(baseline - centre)))
    threshold = max(0.25, 6 * 1.4826 * mad)
    flagged = [
        int(i + len(values) - 6)
        for i, v in enumerate(seasonal[-6:])
        if abs(v - centre) > threshold
    ]
    return {
        "flagged_indices": flagged,
        "threshold": threshold,
        "baseline_median": centre,
        "method": "Recent year-on-year changes compared with the preceding seasonal-change median; threshold is the larger of 25 percentage points or six robust standard deviations. Flags require source-methodology review and do not establish a structural break.",
    }


def train():
    with transaction() as c:
        rows = records(
            c,
            "SELECT period,attendances,release_id FROM mart.ae WHERE grain='national' AND attendance_type='all' ORDER BY period",
        )
    if len(rows) < 30:
        return {
            "status": "withheld",
            "reason": "At least 30 comparable monthly observations are required",
        }
    frame = pd.DataFrame(rows)
    dates = pd.DatetimeIndex(frame.period)
    expected = pd.date_range(dates.min(), dates.max(), freq="MS")
    if len(expected) != len(dates) or frame.attendances.isna().any():
        return {
            "status": "withheld",
            "reason": "Missing reporting months or suppressed national values",
        }
    values = frame.attendances.astype(float).to_numpy()
    comparability = comparability_check(values)
    if comparability["flagged_indices"]:
        return {
            "status": "withheld",
            "reason": "Recent seasonal level shifts require source comparability review",
            "comparability_check": comparability,
        }
    backtests = evaluate(values, dates)
    scores = {}
    for candidate in ["Seasonal naïve", "Damped seasonal ETS"]:
        subset = [
            r for r in backtests if r["candidate"] == candidate and r["horizon"] <= 3
        ]
        error = sum(abs(r["actual"] - r["predicted"]) for r in subset)
        scores[candidate] = {
            "MAE": error / len(subset),
            "WAPE": 100 * error / sum(r["actual"] for r in subset),
        }
    winner = min(scores, key=lambda n: scores[n]["WAPE"])
    future = predict(values, 12, winner)
    forecasts = []
    coverage = {}
    for h, estimate in enumerate(future, 1):
        errors = [
            abs(r["actual"] - r["predicted"])
            for r in backtests
            if r["candidate"] == winner and r["horizon"] == h
        ]
        coverage[str(h)] = len(errors)
        if len(errors) < 6:
            continue
        # Finite-sample conformal order statistic. Sparse horizons are withheld.
        rank = min(len(errors), math.ceil((len(errors) + 1) * 0.9))
        radius = sorted(errors)[rank - 1]
        forecasts.append(
            {
                "period": (dates[-1] + pd.DateOffset(months=h)).date(),
                "horizon": h,
                "estimate": float(estimate),
                "lower": max(0, float(estimate) - radius),
                "upper": float(estimate) + radius,
            }
        )
    metadata = {
        "methodology": "Expanding rolling-origin evaluation; 24-month initial training window. Selection uses MAE/WAPE over horizons 1–3. Empirical 90% absolute-error intervals are calibrated separately by horizon; horizons with fewer than six errors are withheld. These small-sample intervals do not guarantee future coverage.",
        "interval_level": 0.9,
        "horizon_calibration_samples": coverage,
        "candidates": scores,
        "training_start": str(dates[0].date()),
        "observations": len(values),
        "scope": "England, all A&E types, booked-inclusive counts",
        "comparability_check": comparability,
        "comparability": "Aggregate published series; organisational scope and reporting changes may influence results. No patient or bed-availability prediction.",
    }
    with transaction() as c:
        run = c.execute(
            text(
                "INSERT INTO ml.training_run(metric,status,metadata) VALUES('attendances','completed',cast(:m as jsonb)) RETURNING id"
            ),
            {"m": json.dumps(metadata)},
        ).scalar()
        model = c.execute(
            text(
                "INSERT INTO ml.model_version(training_id,name,metric,release_ids,trained_through,metrics,metadata) VALUES(:r,:n,'attendances',:ids,:p,cast(:scores as jsonb),cast(:meta as jsonb)) RETURNING id"
            ),
            {
                "r": run,
                "n": winner,
                "ids": [r["release_id"] for r in rows],
                "p": dates[-1].date(),
                "scores": json.dumps(scores[winner]),
                "meta": json.dumps(metadata),
            },
        ).scalar()
        c.execute(
            text(
                "INSERT INTO ml.backtest(model_id,origin,period,actual,predicted,candidate) VALUES(:id,:origin,:period,:actual,:predicted,:candidate)"
            ),
            [{"id": model, **r} for r in backtests],
        )
        c.execute(
            text(
                "INSERT INTO ml.forecast(model_id,period,horizon,estimate,lower_bound,upper_bound) VALUES(:id,:period,:horizon,:estimate,:lower,:upper)"
            ),
            [{"id": model, **r} for r in forecasts],
        )
    return {
        "status": "trained",
        "model": str(model),
        "winner": winner,
        "scores": scores,
        "forecast_horizons": [r["horizon"] for r in forecasts],
    }


if __name__ == "__main__":
    print(json.dumps(train(), default=str))
