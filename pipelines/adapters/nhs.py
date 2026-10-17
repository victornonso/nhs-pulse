"""Parsers for inspected official NHS files; raw originals remain immutable."""

import calendar
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from dateutil.parser import parse as parse_date
import pandas as pd

MONTHS = {
    name.lower(): number for number, name in enumerate(calendar.month_name) if name
}


def number(value):
    if pd.isna(value) or str(value).strip() in ("", "-", "*", "..", ":", "N/A", "NA"):
        return None
    result = float(str(value).replace(",", "").strip())
    if not __import__("math").isfinite(result):
        return None
    return result


def total(values):
    return None if any(v is None for v in values) else sum(values)


def month(value):
    found = re.search(r"([A-Za-z]+)[\s-]+(20\d\d)", str(value))
    if not found or found[1].lower() not in MONTHS:
        raise ValueError(f"Unrecognised reporting month: {value}")
    return date(int(found[2]), MONTHS[found[1].lower()], 1)


@dataclass
class Parsed:
    period: date
    rows: list[dict]
    table: str
    metadata: dict
    publication: datetime | None = None
    exclusions: list[dict] = field(default_factory=list)


def ae(content: bytes, title: str) -> Parsed:
    frame = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", dtype=str).fillna("")
    required = [
        "Period",
        "Org Code",
        "Parent Org",
        "Org name",
        "A&E attendances Type 1",
        "A&E attendances Type 2",
        "A&E attendances Other A&E Department",
    ]
    if not set(required) <= set(frame.columns):
        raise ValueError("A&E CSV contract changed: required columns missing")
    period = month(frame.loc[frame["Period"] != "TOTAL", "Period"].iloc[0])
    rows = []
    types = [
        ("type1", "Type 1", "Type 1"),
        ("type2", "Type 2", "Type 2"),
        ("other", "Other A&E Department", "Other Department"),
    ]
    for _, r in frame.iterrows():
        code = r["Org Code"].strip().upper()
        if not code:
            continue
        base = {
            "provider_code": "ENGLAND" if code == "TOTAL" else code,
            "period": period,
            "name": "England" if code == "TOTAL" else r["Org name"].strip(),
            "region": None if code == "TOTAL" else r["Parent Org"].strip(),
            "grain": "national" if code == "TOTAL" else "provider",
        }
        bands = {
            k: number(r.get(col, ""))
            for k, col in [
                ("wait_4_12", "Patients who have waited 4-12 hs from DTA to admission"),
                (
                    "wait_12_plus",
                    "Patients who have waited 12+ hrs from DTA to admission",
                ),
                ("other_admissions", "Other emergency admissions"),
            ]
        }
        components = []
        for key, attendance_suffix, other_suffix in types:
            booked = number(
                r.get("A&E attendances Booked Appointments " + other_suffix, "")
            )
            booked_over = number(
                r.get("Attendances over 4hrs Booked Appointments " + other_suffix, "")
            )
            # Missing booked columns are a distinct publication contract, not zero.
            flags = []
            if "A&E attendances Booked Appointments " + other_suffix not in r.index:
                flags.append("Booked appointments not separately published")
                booked = booked_over = 0
            unbooked = number(r["A&E attendances " + attendance_suffix])
            over = number(r.get("Attendances over 4hrs " + other_suffix, ""))
            admission_suffix = (
                attendance_suffix if key != "other" else "Other A&E department"
            )
            row = {
                **base,
                **bands,
                "attendance_type": key,
                "attendances": total([unbooked, booked]),
                "over_four": total([over, booked_over]),
                "booked": booked,
                "booked_over_four": booked_over,
                "admissions": number(
                    r.get("Emergency admissions via A&E - " + admission_suffix, "")
                ),
                "flags": flags,
            }
            components.append(row)
            rows.append(row)
        rows.append(
            {
                **base,
                **bands,
                "attendance_type": "all",
                **{
                    k: total([r[k] for r in components])
                    for k in [
                        "attendances",
                        "over_four",
                        "booked",
                        "booked_over_four",
                        "admissions",
                    ]
                },
                "flags": list({f for r in components for f in r["flags"]}),
            }
        )
    return Parsed(
        period,
        rows,
        "core.ae_monthly",
        {
            "basis": "Includes booked appointments; original non-booked and booked components preserved",
            "original_columns": list(frame.columns),
            "wait_basis": "4–12 and 12+ hours after decision to admit are disjoint bands; neither is arrival-to-departure time",
        },
    )


def beds(content: bytes, title: str, bed_type="overnight") -> Parsed:
    xls = pd.ExcelFile(io.BytesIO(content))
    main = next((s for s in xls.sheet_names if "trust by sector" in s.lower()), None)
    if not main:
        raise ValueError("KH03 workbook missing NHS Trust by Sector")
    frame = pd.read_excel(xls, sheet_name=main, header=None)
    header = next(
        (
            i
            for i, row in frame.iterrows()
            if row.astype(str).str.strip().eq("Org Code").any()
        ),
        None,
    )
    if header is None:
        raise ValueError("KH03 organisation header not found")
    labels = {str(v).strip(): i for i, v in frame.iloc[header].items() if pd.notna(v)}
    # The inspected workbook publishes averages, not a daily observation series.
    yr = str(frame.iloc[header + 1, labels["Year"]])
    end = str(frame.iloc[header + 1, labels["Period End"]])
    end_month = MONTHS.get(end.lower())
    if end_month not in (3, 6, 9, 12):
        raise ValueError("KH03 is not a quarter-end publication")
    year = int(yr[:4]) + (1 if end_month == 3 else 0)
    period = date(year, end_month - 2, 1)
    days = sum(
        calendar.monthrange(year, m)[1] for m in range(end_month - 2, end_month + 1)
    )
    publication = None
    for _, r in frame.iloc[:header].iterrows():
        values = [str(v) for v in r if pd.notna(v)]
        if any(v.strip() == "Published:" for v in values):
            publication = parse_date(values[-1], dayfirst=True).replace(
                hour=9, minute=30
            )
    estimated = set()
    quality = next((s for s in xls.sheet_names if "data quality" in s.lower()), None)
    if quality:
        q = pd.read_excel(xls, sheet_name=quality, header=None)
        for _, row in q.iterrows():
            if len(row) > 1 and re.fullmatch(
                r"[A-Z0-9]{3,8}", str(row.iloc[0]).strip()
            ):
                estimated.add(str(row.iloc[0]).strip())
    rows = []
    sector_names = [
        "Total",
        "General & Acute",
        "Learning Disability",
        "Maternity",
        "Mental Illness",
    ]
    for sheet in [
        main,
        next((s for s in xls.sheet_names if "region by sector" in s.lower()), ""),
    ]:
        if not sheet:
            continue
        d = pd.read_excel(xls, sheet_name=sheet, header=None)
        h = next(
            i
            for i, r in d.iterrows()
            if r.astype(str).str.strip().eq("Period End").any()
        )
        provider = sheet == main
        name_index = 5 if provider else 4
        av_start = 6 if provider else 5
        oc_start = 12 if provider else 11
        for _, r in d.iloc[h + 1 :].iterrows():
            if pd.isna(r.iloc[name_index]):
                continue
            name = str(r.iloc[name_index]).strip()
            if not re.match(r"20\d\d", str(r.iloc[1])):
                continue
            national = name.lower() == "england"
            if national and not provider:
                continue
            code = "ENGLAND" if national else str(r.iloc[4 if provider else 3]).strip()
            if code in ("nan", ""):
                continue
            flags = ["Official estimated return"] if code in estimated else []
            for j, sector in enumerate(sector_names):
                av = number(r.iloc[av_start + j])
                oc = number(r.iloc[oc_start + j])
                rows.append(
                    {
                        "provider_code": code,
                        "quarter": period,
                        "name": name,
                        "region": None if national else str(r.iloc[3]),
                        "grain": "national"
                        if national
                        else "provider"
                        if provider
                        else "region",
                        "bed_type": bed_type,
                        "specialty": sector,
                        "available_average": av,
                        "occupied_average": oc,
                        "available_bed_days": None if av is None else av * days,
                        "occupied_bed_days": None if oc is None else oc * days,
                        "days_in_quarter": days,
                        "flags": flags
                        + (
                            ["Published occupied beds exceed available beds"]
                            if av is not None and oc is not None and oc > av + 0.01
                            else []
                        ),
                    }
                )
    special = next(
        (s for s in xls.sheet_names if "occupied by specialty" in s.lower()), None
    )
    if special:
        d = pd.read_excel(xls, sheet_name=special, header=None)
        h = next(
            i for i, r in d.iterrows() if r.astype(str).str.strip().eq("Org Code").any()
        )
        for _, r in d.iloc[h + 1 :].iterrows():
            if not re.match(r"20\d\d", str(r.iloc[1])) or pd.isna(r.iloc[5]):
                continue
            national = str(r.iloc[5]).strip().lower() == "england"
            code = "ENGLAND" if national else str(r.iloc[4]).strip()
            if code in ("nan", ""):
                continue
            for col in range(6, len(d.columns)):
                name = str(d.iloc[h, col])
                oc = number(r.iloc[col])
                if not re.match(r"^\d{3} ", name):
                    continue
                rows.append(
                    {
                        "provider_code": code,
                        "quarter": period,
                        "name": str(r.iloc[5]).strip(),
                        "region": None if national else str(r.iloc[3]),
                        "grain": "national" if national else "provider",
                        "bed_type": bed_type,
                        "specialty": name,
                        "available_average": None,
                        "occupied_average": oc,
                        "available_bed_days": None,
                        "occupied_bed_days": None if oc is None else oc * days,
                        "days_in_quarter": days,
                        "flags": [
                            "Specialty occupied beds only; no specialty denominator published"
                        ],
                    }
                )
    return Parsed(
        period,
        rows,
        "core.bed_quarterly",
        {
            "raw_unit": "Average daily beds over the quarter",
            "bed_days": "Published average daily beds × actual calendar days in that quarter",
            "original_sheets": xls.sheet_names,
            "cadence": "quarterly",
        },
        publication,
    )


def diagnostics(content: bytes, title: str) -> Parsed:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        members = [i for i in z.infolist() if i.filename.lower().endswith(".csv")]
        if len(members) != 1 or members[0].file_size > 100_000_000:
            raise ValueError("Unexpected diagnostic ZIP members or size")
        frame = pd.read_csv(io.BytesIO(z.read(members[0])), dtype=str).fillna("")
    required = [
        "Period",
        "Provider Org Code",
        "Commissioner Org Code",
        "Diagnostic Tests",
        "Total Activity",
        "Total WL",
    ]
    if not set(required) <= set(frame):
        raise ValueError("DM01 source schema changed")
    period = month(frame["Period"].iloc[0])
    if frame.duplicated(
        ["Provider Org Code", "Commissioner Org Code", "Diagnostic Tests"]
    ).any():
        raise ValueError("Duplicate diagnostic matrix cells")
    frame = frame[frame["Diagnostic Tests"].str.upper() != "TOTAL"].copy()
    measures = ["Total Activity", "Total WL"] + [
        c for c in frame if re.match(r"^\d\d", c)
    ]
    for col in measures:
        frame[col] = pd.to_numeric(
            frame[col].str.replace(",", "", regex=False), errors="coerce"
        )
    bands = [c for c in measures if re.match(r"^\d\d", c)]
    rows = []
    for grain, group_col, name_col in [
        ("provider", "Provider Org Code", "Provider Org Name"),
        ("commissioner", "Commissioner Org Code", "Commissioner Org Name"),
    ]:
        group = frame.groupby([group_col, "Diagnostic Tests"], sort=False)
        sums = group[measures].sum(min_count=1)
        missing = group[measures].count() < group.size().to_numpy()[:, None]
        sums = sums.mask(missing)
        names = group[[name_col, "Provider Parent Org Code"]].first()
        for (code, test), r in sums.iterrows():
            waits = {b: number(r[b]) for b in bands}
            rows.append(
                {
                    "provider_code": str(code) if grain == "provider" else "ALL",
                    "commissioner_code": str(code)
                    if grain == "commissioner"
                    else "ALL",
                    "period": period,
                    "grain": grain,
                    "provider_name": str(names.loc[(code, test), name_col])
                    if grain == "provider"
                    else "All providers",
                    "commissioner_name": str(names.loc[(code, test), name_col])
                    if grain == "commissioner"
                    else "All commissioners",
                    "provider_parent": str(
                        names.loc[(code, test), "Provider Parent Org Code"]
                    )
                    if grain == "provider"
                    else None,
                    "test": str(test),
                    "activity": number(r["Total Activity"]),
                    "waiting_list": number(r["Total WL"]),
                    "waiting_six": total(
                        [v for k, v in waits.items() if int(k[:2]) >= 6]
                    ),
                    "waiting_thirteen": next(
                        (v for k, v in waits.items() if k.startswith("13")), None
                    ),
                    "waiting_bands": waits,
                    "flags": ["Suppression or missing matrix cells preserved"]
                    if any(v is None for v in waits.values())
                    else [],
                }
            )
    exclusions = []
    nonc = frame[frame["Commissioner Org Code"] == "NONC"]
    for (provider, test), group in nonc.groupby(
        ["Provider Org Code", "Diagnostic Tests"]
    ):
        sums = {k: total([number(v) for v in group[k]]) for k in measures}
        waits = {k: sums[k] for k in bands}
        exclusions.append(
            {
                "provider_code": str(provider),
                "test": str(test),
                "activity": sums["Total Activity"],
                "waiting_list": sums["Total WL"],
                "waiting_six": total([v for k, v in waits.items() if int(k[:2]) >= 6]),
                "waiting_thirteen": next(
                    (v for k, v in waits.items() if k.startswith("13")), None
                ),
                "waiting_bands": waits,
            }
        )
    return Parsed(
        period,
        rows,
        "core.diagnostics_monthly",
        {
            "original_grain": "Provider × commissioner × diagnostic test",
            "published_grains": ["provider", "commissioner"],
            "aggregation": "TOTAL test rows excluded; provider and commissioner projections are non-additive",
            "original_columns": list(frame.columns),
        },
        exclusions=exclusions,
    )


def parse(source, content, title):
    if source == "ae":
        return ae(content, title)
    if source.startswith("beds"):
        return beds(content, title, "day" if source.endswith("day") else "overnight")
    if source == "diagnostics":
        return diagnostics(content, title)
    raise ValueError("Unsupported source adapter")
