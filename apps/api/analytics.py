"""SQL owns definitions, filtering, denominators and publication lineage."""

from datetime import date


from .database import fetch


def kpi(label, value, unit, period, provenance=None, detail=None, href=None):

    return {
        "label": label,
        "value": None if value is None else round(float(value), 3),
        "unit": unit,
        "period": str(period) if period else None,
        "provenance": provenance or [],
        "detail": detail,
        "href": href,
    }


def chart(title, rows, x, y, kind="line", unit="", note="", second=None):

    return {
        "title": title,
        "rows": rows,
        "x": x,
        "y": y,
        "kind": kind,
        "unit": unit,
        "note": note,
        "second": second,
    }


async def ae_data(conn, p):

    period = p.get("period")

    if not period:
        period = (await fetch(conn, "SELECT max(period) period FROM mart.ae"))[0][
            "period"
        ]

    params = {**p, "period": period, "type": p.get("type", "all")}

    where = "attendance_type=:type AND grain='national'"

    if p.get("region") or p.get("provider") or p.get("icb"):
        where = "attendance_type=:type AND grain='provider'"

        if p.get("region"):
            where += " AND region=:region"

        if p.get("provider"):
            where += " AND provider_code=:provider"

    if p.get("icb"):
        where += " AND provider_code IN (SELECT r.provider_code FROM ref.organisation_relationship r WHERE r.parent_code=:icb AND r.relationship='ICB' AND r.valid_from<=mart.ae.period AND (r.valid_to IS NULL OR r.valid_to>mart.ae.period))"

    attendance = (
        "attendances"
        if p.get("booked", "include") == "include"
        else "(attendances-booked)"
    )

    over = (
        "over_four"
        if p.get("booked", "include") == "include"
        else "(over_four-booked_over_four)"
    )

    aggregate = f"sum({attendance}) AS attendances,sum({over}) AS over_four,100.0*sum({attendance}-{over})/nullif(sum({attendance}) FILTER(WHERE {attendance} IS NOT NULL AND {over} IS NOT NULL),0) AS four_hour_pct,sum(admissions) AS admissions,sum(other_admissions) AS other_admissions,sum(wait_4_12) AS wait_4_12,sum(wait_12_plus) AS wait_12_plus,count(*) AS organisations,count(*) FILTER(WHERE {attendance} IS NULL OR {over} IS NULL) AS missing_rows"

    summary = (
        await fetch(
            conn,
            f"SELECT {aggregate} FROM mart.ae WHERE {where} AND period=:period",
            params,
        )
    )[0]

    trend = await fetch(
        conn,
        f"SELECT period,{aggregate} FROM mart.ae WHERE {where} AND period<=:period AND period>:period-interval '36 months' GROUP BY period ORDER BY period",
        params,
    )

    provider_where = "grain='provider' AND attendance_type=:type AND period=:period"

    if p.get("region"):
        provider_where += " AND region=:region"

    if p.get("provider"):
        provider_where += " AND provider_code=:provider"

    if p.get("icb"):
        provider_where += " AND provider_code IN (SELECT r.provider_code FROM ref.organisation_relationship r WHERE r.parent_code=:icb AND r.relationship='ICB' AND r.valid_from<=mart.ae.period AND (r.valid_to IS NULL OR r.valid_to>mart.ae.period))"

    providers = await fetch(
        conn,
        f"SELECT provider_code code,name,region,{attendance} attendances,{over} over_four,100.0*({attendance}-{over})/nullif({attendance},0) AS four_hour_pct,admissions,wait_12_plus,flags,release_id,official_url FROM mart.ae WHERE {provider_where} ORDER BY attendances DESC NULLS LAST",
        params,
    )

    distribution = await fetch(
        conn,
        f"SELECT CASE WHEN rate>=85 THEN '85% and above' WHEN rate>=75 THEN '75–85%' WHEN rate>=65 THEN '65–75%' ELSE 'Below 65%' END band,count(*) providers FROM (SELECT 100.0*({attendance}-{over})/nullif({attendance},0) rate FROM mart.ae WHERE {provider_where} AND {attendance}>0) t GROUP BY 1 ORDER BY 1",
        params,
    )

    regions = await fetch(
        conn,
        f"SELECT region, sum({attendance}) attendances,100.0*sum({attendance}-{over})/nullif(sum({attendance}) FILTER(WHERE {attendance} IS NOT NULL AND {over} IS NOT NULL),0) four_hour_pct,count(*) providers FROM mart.ae WHERE grain='provider' AND attendance_type=:type AND period=:period GROUP BY region ORDER BY four_hour_pct DESC",
        params,
    )

    provenance = await fetch(
        conn,
        f"SELECT DISTINCT release_id,official_publication,ingested_at,official_url,version FROM mart.ae WHERE {where} AND period=:period",
        params,
    )

    if p.get("type", "all") != "all":
        # Official DTA bands are provider totals, without a department breakdown.
        for row in [summary, *trend, *providers]:
            row["wait_4_12"] = row["wait_12_plus"] = None

    return {
        "period": period,
        "summary": summary,
        "trend": trend,
        "providers": providers,
        "distribution": distribution,
        "regions": regions,
        "provenance": provenance,
    }


async def bed_data(conn, p):

    period = p.get("period") or date.today()

    bed_type = p.get("bed_type", "overnight")

    quarter = (
        await fetch(
            conn,
            "SELECT max(quarter) quarter FROM mart.beds WHERE bed_type=:bed_type AND quarter<=:period",
            {"period": period, "bed_type": bed_type},
        )
    )[0]["quarter"]

    params = {**p, "quarter": quarter, "bed_type": bed_type}

    where = "bed_type=:bed_type AND specialty='Total' AND grain='national'"

    if p.get("provider"):
        where = "bed_type=:bed_type AND specialty='Total' AND grain='provider' AND provider_code=:provider"

    summary = (
        await fetch(
            conn,
            f"SELECT sum(available_bed_days) available_bed_days,sum(occupied_bed_days) occupied_bed_days,sum(available_average) available_average,sum(occupied_average) occupied_average,100.0*sum(occupied_bed_days) FILTER(WHERE available_bed_days IS NOT NULL)/nullif(sum(available_bed_days) FILTER(WHERE occupied_bed_days IS NOT NULL),0) occupancy FROM mart.beds WHERE {where} AND quarter=:quarter",
            params,
        )
    )[0]

    trend = await fetch(
        conn,
        f"SELECT quarter,sum(available_average) available_average,sum(occupied_average) occupied_average,100.0*sum(occupied_bed_days) FILTER(WHERE available_bed_days IS NOT NULL)/nullif(sum(available_bed_days) FILTER(WHERE occupied_bed_days IS NOT NULL),0) occupancy FROM mart.beds WHERE {where} AND quarter<=:quarter GROUP BY quarter ORDER BY quarter",
        params,
    )

    providers = await fetch(
        conn,
        "SELECT provider_code code,name,region,available_average,occupied_average,available_bed_days,occupied_bed_days,100.0*occupied_bed_days/nullif(available_bed_days,0) occupancy,flags,release_id,official_url FROM mart.beds WHERE quarter=:quarter AND bed_type=:bed_type AND specialty='Total' AND grain='provider' ORDER BY occupancy DESC NULLS LAST",
        params,
    )

    specialties = await fetch(
        conn,
        "SELECT specialty,occupied_average,available_average,occupied_bed_days,available_bed_days FROM mart.beds WHERE quarter=:quarter AND bed_type=:bed_type AND grain='national' AND specialty<>'Total' ORDER BY occupied_average DESC NULLS LAST",
        params,
    )

    provenance = await fetch(
        conn,
        f"SELECT DISTINCT release_id,official_publication,ingested_at,official_url,version FROM mart.beds WHERE {where} AND quarter=:quarter",
        params,
    )

    return {
        "quarter": quarter,
        "summary": summary,
        "trend": trend,
        "providers": providers,
        "specialties": specialties,
        "provenance": provenance,
    }


async def diagnostic_data(conn, p):

    period = (
        await fetch(
            conn,
            "SELECT max(period) period FROM mart.diagnostics WHERE period<=:period",
            {"period": p.get("period") or date.today()},
        )
    )[0]["period"]

    params = {**p, "period": period, "grain": p.get("diagnostic_grain", "provider")}

    where = "grain=:grain"

    if p.get("provider") and params["grain"] == "provider":
        where += " AND provider_code=:provider"

    summary = (
        await fetch(
            conn,
            f"SELECT sum(activity) activity,sum(waiting_list) waiting_list,sum(waiting_six) waiting_six,sum(waiting_thirteen) waiting_thirteen,100.0*sum(waiting_six) FILTER(WHERE waiting_list IS NOT NULL)/nullif(sum(waiting_list) FILTER(WHERE waiting_six IS NOT NULL),0) six_week_pct FROM mart.diagnostics WHERE {where} AND period=:period",
            params,
        )
    )[0]

    tests = await fetch(
        conn,
        f"SELECT test,sum(activity) activity,sum(waiting_list) waiting_list,sum(waiting_six) waiting_six,100.0*sum(waiting_six) FILTER(WHERE waiting_list IS NOT NULL)/nullif(sum(waiting_list) FILTER(WHERE waiting_six IS NOT NULL),0) six_week_pct FROM mart.diagnostics WHERE {where} AND period=:period GROUP BY test ORDER BY activity DESC",
        params,
    )

    trend = await fetch(
        conn,
        f"SELECT period,sum(activity) activity,sum(waiting_six) waiting_six,sum(waiting_list) waiting_list,100.0*sum(waiting_six) FILTER(WHERE waiting_list IS NOT NULL)/nullif(sum(waiting_list) FILTER(WHERE waiting_six IS NOT NULL),0) six_week_pct FROM mart.diagnostics WHERE {where} AND period<=:period GROUP BY period ORDER BY period",
        params,
    )

    provenance = await fetch(
        conn,
        f"SELECT DISTINCT release_id,official_publication,ingested_at,official_url,version FROM mart.diagnostics WHERE {where} AND period=:period",
        params,
    )

    return {
        "period": period,
        "summary": summary,
        "tests": tests,
        "trend": trend,
        "provenance": provenance,
    }


async def operations(conn):

    return {
        "sources": await fetch(
            conn, "SELECT * FROM mart.collection_status ORDER BY id"
        ),
        "runs": await fetch(
            conn, "SELECT * FROM ops.ingestion_run ORDER BY started_at DESC LIMIT 100"
        ),
        "releases": await fetch(
            conn,
            "SELECT r.*,a.content_sha256 FROM ops.release_version r JOIN raw.asset a ON a.id=r.asset_id ORDER BY r.created_at DESC LIMIT 100",
        ),
        "calendar": await fetch(
            conn,
            "SELECT c.*,s.name FROM ops.publication_calendar c JOIN ops.source s ON s.id=c.source_id WHERE c.expected_at>=now()-interval '35 days' ORDER BY expected_at,source_id",
        ),
        "quality": await fetch(
            conn,
            "SELECT * FROM ops.validation_result ORDER BY checked_at DESC LIMIT 100",
        ),
        "events": await fetch(
            conn, "SELECT * FROM ops.pipeline_event ORDER BY at DESC LIMIT 100"
        ),
    }


async def workspace(conn, screen, p):

    ae = await ae_data(conn, p)

    bed = await bed_data(conn, p)

    dx = await diagnostic_data(conn, p)

    source_rows = await fetch(
        conn,
        "SELECT id,name,cadence,last_checked,last_ingested,status FROM ops.source ORDER BY id",
    )

    result = {
        "screen": screen,
        "period": ae["period"],
        "quarter": bed["quarter"],
        "diagnostic_period": dx["period"],
        "sources": source_rows,
        "metrics": [],
        "charts": [],
        "table": [],
        "provenance": {
            "ae": ae["provenance"],
            "beds": bed["provenance"],
            "diagnostics": dx["provenance"],
        },
        "notes": [
            "Independent analysis using published NHS England statistics.",
            "Publication statistics describe historical reporting periods; they are not live hospital conditions.",
        ],
        "generation": (
            await fetch(
                conn,
                "SELECT coalesce(sum(generation),0) generation FROM ops.mart_publication",
            )
        )[0]["generation"],
    }

    if screen in ("overview", "emergency", "trusts", "geography"):
        s = ae["summary"]
        admissions = (
            (
                s["admissions"] + s["other_admissions"]
                if s["admissions"] is not None and s["other_admissions"] is not None
                else None
            )
            if p.get("type", "all") == "all"
            else s["admissions"]
        )

        result["metrics"] = [
            kpi(
                "A&E attendances",
                s["attendances"],
                "attendances",
                ae["period"],
                ae["provenance"],
                f"{p.get('type', 'all')} departments · booked appointments {p.get('booked', 'include')}d",
                "/emergency",
            ),
            kpi(
                "Within four hours",
                s["four_hour_pct"],
                "%",
                ae["period"],
                ae["provenance"],
                "Same attendance denominator",
                "/emergency",
            ),
            kpi(
                "Emergency admissions",
                admissions,
                "admissions",
                ae["period"],
                ae["provenance"],
                "All routes"
                if p.get("type", "all") == "all"
                else "Selected department route",
                "/emergency",
            ),
            kpi(
                "12+ hours after decision to admit",
                s["wait_12_plus"],
                "patients",
                ae["period"],
                ae["provenance"],
                "Decision-to-admit measure"
                if p.get("type", "all") == "all"
                else "Published for all departments only",
                "/emergency",
            ),
        ]

        result["charts"] = [
            chart(
                "A&E activity and performance",
                ae["trend"],
                "period",
                "attendances",
                "combo",
                "attendances",
                "Monthly published statistics",
                second="four_hour_pct",
            ),
            chart(
                "Provider distribution",
                ae["distribution"],
                "band",
                "providers",
                "bar",
                "providers",
                "Providers with a positive attendance denominator",
            ),
            chart(
                "Regional variation",
                ae["regions"],
                "region",
                "four_hour_pct",
                "horizontal",
                "%",
                "Weighted provider aggregates on the published region assignment",
            ),
        ]

        result["table"] = ae["providers"]
        result["table_kind"] = "ae"
        result["regions"] = ae["regions"]

        if screen == "overview":
            result["metrics"][3] = kpi(
                "KH03 bed occupancy",
                bed["summary"]["occupancy"],
                "%",
                bed["quarter"],
                bed["provenance"],
                "Quarterly · overnight beds",
                "/capacity",
            )

            result["charts"].append(
                chart(
                    "Diagnostic activity",
                    dx["tests"],
                    "test",
                    "activity",
                    "horizontal",
                    "tests",
                    f"Fifteen tests · {dx['period'].strftime('%b %Y') if dx['period'] else 'Unavailable'} · provider grain",
                )
            )

        if screen == "emergency":
            result["charts"].append(
                chart(
                    "Waits after decision to admit",
                    [
                        {"band": "4–12 hours", "patients": s["wait_4_12"]},
                        {"band": "12+ hours", "patients": s["wait_12_plus"]},
                    ],
                    "band",
                    "patients",
                    "bar",
                    "patients",
                    "Disjoint waiting bands; not time since arrival"
                    if p.get("type", "all") == "all"
                    else "Department-specific DTA bands are not published",
                )
            )

        if screen == "geography":
            result["geography"] = await fetch(
                conn,
                "SELECT code,name,valid_from,valid_to FROM geo.icb_boundary ORDER BY name",
            )

    if screen == "capacity":
        s = bed["summary"]
        result["metrics"] = [
            kpi(
                "Available bed-days",
                s["available_bed_days"],
                "bed-days",
                bed["quarter"],
                bed["provenance"],
                "Quarterly denominator",
            ),
            kpi(
                "Occupied bed-days",
                s["occupied_bed_days"],
                "bed-days",
                bed["quarter"],
                bed["provenance"],
                "Quarterly numerator",
            ),
            kpi(
                "Bed occupancy",
                s["occupancy"],
                "%",
                bed["quarter"],
                bed["provenance"],
                "Occupied / available bed-days",
            ),
            kpi(
                "Average available beds",
                s["available_average"],
                "beds",
                bed["quarter"],
                bed["provenance"],
                "Published average daily number over the quarter",
            ),
        ]

        result["charts"] = [
            chart(
                "Capacity across published quarters",
                bed["trend"],
                "quarter",
                "available_average",
                "line",
                "average beds",
                "No monthly or daily interpolation",
                second="occupied_average",
            ),
            chart(
                "Occupancy by quarter",
                bed["trend"],
                "quarter",
                "occupancy",
                "bar",
                "%",
                "Within-quarter denominators",
            ),
            chart(
                "Occupied beds by specialty",
                bed["specialties"][:20],
                "specialty",
                "occupied_average",
                "horizontal",
                "average beds",
                "Specialty occupancy rates require matching specialty denominators",
            ),
        ]

        result["table"] = bed["providers"]
        result["table_kind"] = "beds"
        result["notes"].append(
            "KH03 is a quarterly publication. Average daily beds are not a count of currently free beds."
        )

    if screen == "forecasting":
        models = await fetch(
            conn,
            "SELECT * FROM ml.model_version WHERE trained_through<=:period ORDER BY trained_through DESC,name",
            {"period": ae["period"]},
        )
        result["models"] = models

        chosen = models[0] if models else None

        result["metrics"] = [
            kpi(
                "Published months",
                len(ae["trend"]),
                "months",
                ae["period"],
                ae["provenance"],
            ),
            kpi("Forecast horizon", p.get("horizon", 3), "months", ae["period"], {}),
            kpi(
                "Model selection",
                None,
                "",
                ae["period"],
                {},
                "Rolling-origin benchmark",
            ),
        ]

        result["charts"] = [
            chart(
                "Published attendance history",
                ae["trend"],
                "period",
                "attendances",
                "line",
                "attendances",
                "Monthly aggregate counts only",
            )
        ]

        if chosen:
            result["metrics"] = [
                result["metrics"][0],
                result["metrics"][1],
                kpi(
                    "Backtest MAE",
                    chosen["metrics"]["MAE"],
                    "attendances",
                    ae["period"],
                    ae["provenance"],
                    "Rolling-origin horizons 1-3",
                ),
                kpi(
                    "Backtest WAPE",
                    chosen["metrics"]["WAPE"],
                    "%",
                    ae["period"],
                    ae["provenance"],
                    "Volume-weighted absolute error",
                ),
            ]

            forecast = await fetch(
                conn,
                "SELECT * FROM ml.forecast WHERE model_id=:model AND horizon<=:horizon ORDER BY period",
                {"model": chosen["id"], "horizon": p.get("horizon", 3)},
            )

            backtests = await fetch(
                conn,
                "SELECT * FROM ml.backtest WHERE model_id=:model ORDER BY origin,period",
                {"model": chosen["id"]},
            )

            result["forecast"] = forecast
            result["backtests"] = backtests
            result["selected_model"] = chosen

            result["charts"].append(
                chart(
                    "Forecast and empirical interval",
                    forecast,
                    "period",
                    "estimate",
                    "forecast",
                    "attendances",
                    "Intervals calibrated separately by horizon",
                )
            )

            result["charts"].append(
                chart(
                    "Rolling-origin forecast errors",
                    [
                        {**r, "error": float(r["predicted"]) - float(r["actual"])}
                        for r in backtests
                    ],
                    "period",
                    "error",
                    "bar",
                    "attendances",
                    "Predictions use only observations available at each origin",
                )
            )

        else:
            result["forecast"] = []
            result["notes"].append(
                "Forecasts are withheld until sufficient comparable observations and backtests are available."
            )

    if screen == "operations":
        ops = await operations(conn)
        result.update(ops)

        result["metrics"] = [
            kpi("Configured sources", len(ops["sources"]), "sources", None),
            kpi(
                "Published versions",
                sum(r["status"] == "published" for r in ops["releases"]),
                "versions",
                None,
            ),
            kpi(
                "Historical revisions",
                sum(r["revision_of"] is not None for r in ops["releases"]),
                "versions",
                None,
            ),
            kpi(
                "Quarantined releases",
                sum(r["status"] == "quarantined" for r in ops["releases"]),
                "versions",
                None,
            ),
        ]

        result["table"] = ops["runs"]
        result["table_kind"] = "operations"

    if screen == "analyst":
        result["catalogue"] = await fetch(
            conn, "SELECT * FROM ref.metric_definition ORDER BY id"
        )

    result["coverage"] = {
        "ae_missing_rows": ae["summary"]["missing_rows"],
        "ae_organisations": ae["summary"]["organisations"],
        "diagnostic_grain": p.get("diagnostic_grain", "provider"),
    }

    return result
