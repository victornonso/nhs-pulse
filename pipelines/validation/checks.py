import math


def validate(parsed):
    checks = []

    def check(name, passed, detail, critical=True):
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "severity": "critical" if critical else "warning",
                "detail": detail,
            }
        )

    check("nonempty_release", len(parsed.rows) > 0, {"rows": len(parsed.rows)})
    numeric = [
        (key, value)
        for row in parsed.rows
        for key, value in row.items()
        if isinstance(value, (float, int)) and not isinstance(value, bool)
    ]
    check(
        "finite_nonnegative_values",
        all(math.isfinite(v) and v >= 0 for _, v in numeric),
        {},
    )
    if parsed.table == "core.ae_monthly":
        check(
            "one_reporting_month",
            all(r["period"] == parsed.period for r in parsed.rows),
            {},
        )
        check(
            "waits_within_attendances",
            all(
                r["over_four"] is None
                or r["attendances"] is None
                or r["over_four"] <= r["attendances"]
                for r in parsed.rows
            ),
            {},
        )
        national = [r for r in parsed.rows if r["grain"] == "national"]
        check("national_rows", len(national) == 4, {"rows": len(national)})
        for n in national:
            providers = [
                r
                for r in parsed.rows
                if r["grain"] == "provider"
                and r["attendance_type"] == n["attendance_type"]
            ]
            for key in ["attendances", "over_four", "admissions"]:
                complete = n[key] is not None and all(
                    r[key] is not None for r in providers
                )
                check(
                    f"provider_national_{n['attendance_type']}_{key}",
                    not complete or abs(sum(r[key] for r in providers) - n[key]) < 0.01,
                    {"national": n[key], "complete": complete},
                )
    if parsed.table == "core.bed_quarterly":
        check(
            "quarter_grain",
            parsed.period.month in (1, 4, 7, 10)
            and all(90 <= r["days_in_quarter"] <= 92 for r in parsed.rows),
            {},
        )
        check(
            "occupancy_not_above_capacity",
            all(
                r["occupied_average"] is None
                or r["available_average"] is None
                or r["occupied_average"] <= r["available_average"] + 0.01
                for r in parsed.rows
            ),
            {
                "policy": "Retain official values and flag the anomaly; do not silently cap occupancy"
            },
            critical=False,
        )
        check(
            "national_total",
            len(
                [
                    r
                    for r in parsed.rows
                    if r["grain"] == "national" and r["specialty"] == "Total"
                ]
            )
            == 1,
            {},
        )
        for key in ["available_average", "occupied_average"]:
            provider = [
                r[key]
                for r in parsed.rows
                if r["grain"] == "provider" and r["specialty"] == "Total"
            ]
            n = next(
                (
                    r[key]
                    for r in parsed.rows
                    if r["grain"] == "national" and r["specialty"] == "Total"
                ),
                None,
            )
            complete = n is not None and all(v is not None for v in provider)
            check(
                "bed_national_" + key,
                not complete or abs(sum(provider) - n) < 0.1,
                {"complete": complete},
            )
    if parsed.table == "core.diagnostics_monthly":
        check(
            "waiting_band_denominator",
            all(
                r["waiting_six"] is None
                or r["waiting_list"] is None
                or r["waiting_six"] <= r["waiting_list"]
                for r in parsed.rows
            ),
            {},
        )
        check(
            "no_total_test_double_counting",
            all(r["test"] != "TOTAL" for r in parsed.rows),
            {},
        )
        check(
            "two_disjoint_grains",
            {r["grain"] for r in parsed.rows} == {"provider", "commissioner"},
            {},
        )
        for key in ["activity", "waiting_list"]:
            sums = {
                g: sum(r[key] or 0 for r in parsed.rows if r["grain"] == g)
                for g in ["provider", "commissioner"]
            }
            check(
                "grain_reconciliation_" + key,
                abs(sums["provider"] - sums["commissioner"]) < 0.01,
                sums,
            )
    return checks
