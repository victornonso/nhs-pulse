import json
import re
from datetime import datetime, UTC
from zoneinfo import ZoneInfo
import httpx
from pypdf import PdfReader
from sqlalchemy import text
from apps.api.database import transaction
from apps.api.settings import ROOT
from pipelines.discovery.sources import SOURCES

CALENDAR = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/04/Proposed-12-month-plan-for-2026-27-for-publication-3.pdf"
METRICS = [
    (
        "attendances",
        "A&E attendances",
        "attendances",
        "All attendances of the selected department type, including booked appointments.",
        "ae",
        "attendances",
        None,
    ),
    (
        "four_hour_pct",
        "Within four hours",
        "%",
        "100 × (attendances minus over-four-hour attendances) / attendances, on the same booked/type basis.",
        "ae",
        "attendances - over_four",
        "attendances",
    ),
    (
        "emergency_admissions",
        "Emergency admissions",
        "admissions",
        "A&E admissions plus other emergency admissions for the all-types measure.",
        "ae",
        "admissions + other_admissions",
        None,
    ),
    (
        "dta_twelve",
        "12+ hours after decision to admit",
        "patients",
        "Published count waiting twelve or more hours from decision to admit to admission. This is not arrival-to-departure time.",
        "ae",
        "wait_12_plus",
        None,
    ),
    (
        "bed_occupancy",
        "Quarterly bed occupancy",
        "%",
        "100 × occupied bed-days / available bed-days, within the same quarter, bed type and sector. Published daily averages are multiplied by calendar days in the quarter.",
        "beds_overnight",
        "occupied_bed_days",
        "available_bed_days",
    ),
    (
        "diagnostic_activity",
        "Diagnostic activity",
        "tests",
        "Published tests conducted, aggregated over the fifteen named tests with TOTAL rows excluded. Provider and commissioner grains must never be combined.",
        "diagnostics",
        "activity",
        None,
    ),
    (
        "diagnostic_six",
        "Waiting six weeks or more",
        "%",
        "100 × sum of six-week-and-over waiting bands / total waiting list, on one diagnostic grain.",
        "diagnostics",
        "waiting_six",
        "waiting_list",
    ),
]


def main():
    with transaction() as conn:
        for key, s in SOURCES.items():
            policy = {
                "revision_check_hours": 24,
                "release_window_hours": 6,
                "release_check_minutes": 60,
                "delay_grace_hours": 72,
                "timezone": "Europe/London",
            }
            conn.execute(
                text(
                    "INSERT INTO ops.source(id,name,page_url,cadence,enabled,policy) VALUES(:id,:name,:url,:cadence,:enabled,cast(:policy as jsonb)) ON CONFLICT(id) DO UPDATE SET page_url=excluded.page_url,policy=excluded.policy"
                ),
                {
                    "id": key,
                    "name": s["name"],
                    "url": s["page"],
                    "cadence": s["cadence"],
                    "enabled": s.get("enabled", True),
                    "policy": json.dumps(policy),
                },
            )
        for key, label, unit, definition, source, numerator, denominator in METRICS:
            conn.execute(
                text(
                    "INSERT INTO ref.metric_definition(id,label,unit,definition,source_id,numerator,denominator) VALUES(:id,:label,:unit,:definition,:source,:num,:den) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition"
                ),
                {
                    "id": key,
                    "label": label,
                    "unit": unit,
                    "definition": definition,
                    "source": source,
                    "num": numerator,
                    "den": denominator,
                },
            )
        conn.execute(
            text(
                "INSERT INTO ref.calendar SELECT d::date,date_trunc('month',d)::date,date_trunc('quarter',d)::date,(date_trunc('quarter',d)+interval '3 months'-date_trunc('quarter',d))::interval/interval '1 day' FROM generate_series('2020-01-01'::timestamp,'2030-12-31',interval '1 day') d ON CONFLICT DO NOTHING".replace(
                    "(date_trunc('quarter',d)+interval '3 months'-date_trunc('quarter',d))::interval/interval '1 day'",
                    "extract(day from (date_trunc('quarter',d)+interval '3 months'-date_trunc('quarter',d)))::int",
                )
            )
        )
    path = ROOT / ".local/publication-calendar.pdf"
    if not path.exists():
        response = httpx.get(CALENDAR, timeout=90, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)
    layout = "\n".join(
        p.extract_text(extraction_mode="layout") for p in PdfReader(path).pages
    )
    entries = []
    for match in re.finditer(
        r"(\d{2}/\d{2}/\d{4})\s+([^\n]+(?:\n(?!\s*\d{2}/\d{2}/\d{4})[^\n]+)*)", layout
    ):
        day, title = match.groups()
        title = " ".join(title.split())
        source = (
            "ae"
            if title.startswith("A&E attendances")
            else "diagnostics"
            if title.startswith("Diagnostic waiting times and activity")
            else "beds_overnight"
            if title.startswith("Bed availability and occupancy data")
            else None
        )
        if source is None:
            continue
        expected = datetime.strptime(day, "%d/%m/%Y").replace(
            hour=9, minute=30, tzinfo=ZoneInfo("Europe/London")
        )
        from pipelines.adapters.nhs import month

        try:
            period = month(title)
        except ValueError:
            period = None
        entries.append(
            {"source": source, "period": period, "at": expected, "title": title}
        )
        if source == "beds_overnight":
            entries.append(
                {"source": "beds_day", "period": period, "at": expected, "title": title}
            )
    with transaction() as conn:
        for e in entries:
            conn.execute(
                text(
                    "INSERT INTO ops.publication_calendar(source_id,reporting_period,expected_at,official_url) VALUES(:source,:period,:at,:url) ON CONFLICT(source_id,expected_at) DO NOTHING"
                ),
                {**e, "url": CALENDAR},
            )
    print(
        "Sources and metric definitions seeded; official calendar entries:",
        len(entries),
    )
    (ROOT / "docs/calendar-extract.json").write_text(
        json.dumps(
            {
                "source": CALENDAR,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "entries": entries,
            },
            default=str,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
