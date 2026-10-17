import csv
import io
import json
import hmac
import time
from datetime import date, datetime, UTC, timedelta
from typing import Literal
from uuid import UUID, uuid4
from collections import defaultdict, deque
import jwt
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from .settings import settings
from .schemas import Dashboard
from .cache import published_workspace
from .database import read_session, fetch
from .analytics import workspace, ae_data, bed_data, diagnostic_data, operations

SCREENS = (
    "overview",
    "emergency",
    "capacity",
    "trusts",
    "geography",
    "forecasting",
    "analyst",
    "operations",
)
app = FastAPI(
    title="NHS Pulse API",
    version="1.0.0",
    description="Independent analysis using published NHS England aggregate statistics. No patient or live operational feed.",
)
limits = defaultdict(deque)


@app.exception_handler(Exception)
async def unexpected(request, exc):
    import logging

    logging.getLogger("nhs.api").exception("Analytical request failed", exc_info=exc)
    return JSONResponse(
        {
            "detail": "The analytical service could not complete this request. Please retry shortly."
        },
        500,
    )


@app.middleware("http")
async def boundary(request, call_next):
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = limits[ip]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= 180:
        return JSONResponse(
            {"detail": "Request limit reached. Retry shortly."},
            429,
            headers={"Retry-After": "60"},
        )
    window.append(now)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin != settings.app_origin:
            return JSONResponse({"detail": "Origin is not authorised."}, 403)
    request.state.visitor = None
    token = request.cookies.get("nhs_pulse_visitor", "")
    fresh = False
    try:
        claims = jwt.decode(
            token,
            settings.session_secret,
            algorithms=["HS256"],
            audience="nhs-pulse",
            options={"require": ["sub", "exp", "aud"]},
        )
        request.state.visitor = str(UUID(claims["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError):
        request.state.visitor = str(uuid4())
        fresh = True
    response = await call_next(request)
    if fresh:
        token = jwt.encode(
            {
                "sub": request.state.visitor,
                "aud": "nhs-pulse",
                "exp": datetime.now(UTC) + timedelta(days=30),
            },
            settings.session_secret,
            algorithm="HS256",
        )
        response.set_cookie(
            "nhs_pulse_visitor",
            token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            max_age=30 * 86400,
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Request-ID"] = str(uuid4())
    return response


def params(
    period=None,
    region=None,
    provider=None,
    type="all",
    booked="include",
    bed_type="overnight",
    diagnostic_grain="provider",
    horizon=3,
    icb=None,
):
    if period:
        try:
            period = date.fromisoformat(period + "-01")
        except ValueError as e:
            raise HTTPException(422, "Use a valid YYYY-MM reporting month.") from e
    return locals()


@app.get("/health/live")
def live():
    return {"status": "live"}


@app.get("/health/ready")
async def ready():
    async with read_session() as conn:
        status = await fetch(
            conn,
            "SELECT postgis_lib_version() spatial,(SELECT count(*) FROM ops.mart_publication) publications",
        )
    return {"status": "ready", **status[0]}


@app.get("/api/v1/workspace/{screen}", response_model=Dashboard)
async def screen_data(
    screen: Literal[
        "overview",
        "emergency",
        "capacity",
        "trusts",
        "geography",
        "forecasting",
        "analyst",
        "operations",
    ],
    request: Request,
    period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    region: str | None = Query(None, max_length=100),
    provider: str | None = Query(None, pattern="^[A-Z0-9]{3,8}$"),
    type: Literal["all", "type1", "type2", "other"] = "all",
    booked: Literal["include", "exclude"] = "include",
    bed_type: Literal["overnight", "day"] = "overnight",
    diagnostic_grain: Literal["provider", "commissioner"] = "provider",
    horizon: int = Query(3, ge=1, le=12),
    icb: str | None = Query(None, pattern="^[A-Z0-9]{3,8}$"),
):
    async with read_session() as conn:
        result = await published_workspace(
            conn,
            screen,
            params(
                period,
                region,
                provider,
                type,
                booked,
                bed_type,
                diagnostic_grain,
                horizon,
                icb,
            ),
        )
        if screen == "analyst":
            result["configured"] = bool(settings.llm_api_key)
            result["conversations"] = await fetch(
                conn,
                "SELECT id,question,status,created_at FROM ai.conversation WHERE session_id=:session ORDER BY created_at DESC LIMIT 30",
                {"session": request.state.visitor},
            )
    return result


@app.get("/api/v1/metadata/{kind}")
async def metadata(kind: Literal["metrics", "periods", "organisation-types"]):
    async with read_session() as conn:
        if kind == "metrics":
            return await fetch(conn, "SELECT * FROM ref.metric_definition ORDER BY id")
        if kind == "periods":
            return {
                "months": await fetch(
                    conn, "SELECT DISTINCT period FROM mart.ae ORDER BY period DESC"
                ),
                "quarters": await fetch(
                    conn, "SELECT DISTINCT quarter FROM mart.beds ORDER BY quarter DESC"
                ),
                "diagnostics": await fetch(
                    conn,
                    "SELECT DISTINCT period FROM mart.diagnostics ORDER BY period DESC",
                ),
            }
        return await fetch(
            conn, "SELECT DISTINCT org_type FROM ref.organisation ORDER BY org_type"
        )


@app.get("/api/v1/overview")
async def overview(period: str | None = None):
    async with read_session() as conn:
        return await workspace(conn, "overview", params(period))


@app.get("/api/v1/publication-generation")
async def publication_generation():
    async with read_session() as conn:
        return (
            await fetch(
                conn,
                "SELECT coalesce(sum(generation),0) generation FROM ops.mart_publication",
            )
        )[0]


@app.get("/api/v1/ae/{view}")
async def ae_endpoint(
    view: Literal["summary", "trend", "providers", "distribution"],
    period: str | None = None,
    type: Literal["all", "type1", "type2", "other"] = "all",
    booked: Literal["include", "exclude"] = "include",
    region: str | None = Query(None, max_length=100),
):
    async with read_session() as conn:
        data = await ae_data(conn, params(period, region, type=type, booked=booked))
    return {
        "data": data[view],
        "reporting_period": data["period"],
        "provenance": data["provenance"],
    }


@app.get("/api/v1/beds/{view}")
async def bed_endpoint(
    view: Literal["summary", "trend", "specialties", "providers"],
    period: str | None = None,
    bed_type: Literal["overnight", "day"] = "overnight",
):
    async with read_session() as conn:
        data = await bed_data(conn, params(period, bed_type=bed_type))
    return {
        "data": data[view],
        "reporting_quarter": data["quarter"],
        "provenance": data["provenance"],
    }


@app.get("/api/v1/diagnostics/{view}")
async def diagnostic_endpoint(
    view: Literal["summary", "trend", "tests"],
    period: str | None = None,
    grain: Literal["provider", "commissioner"] = "provider",
):
    async with read_session() as conn:
        data = await diagnostic_data(conn, params(period, diagnostic_grain=grain))
    return {
        "data": data[view],
        "reporting_period": data["period"],
        "grain": grain,
        "provenance": data["provenance"],
    }


@app.get("/api/v1/operations/{view}")
async def operational_endpoint(
    view: Literal["sources", "calendar", "releases", "runs", "quality", "revisions"],
):
    async with read_session() as conn:
        data = await operations(conn)
    return (
        [r for r in data["releases"] if r["revision_of"]]
        if view == "revisions"
        else data[view]
    )


class Discovery(BaseModel):
    source: Literal["ae", "beds_overnight", "beds_day", "diagnostics"]
    backfill: int = Field(1, ge=1, le=48)


@app.post("/api/v1/operations/discover")
async def discover(body: Discovery, request: Request):
    if not settings.admin_key or not hmac.compare_digest(
        request.headers.get("x-admin-key", ""), settings.admin_key
    ):
        raise HTTPException(403, "Operational discovery requires administrator access.")
    from starlette.concurrency import run_in_threadpool
    from pipelines.orchestration.collect import collect

    return await run_in_threadpool(collect, body.source, body.backfill, True)


@app.get("/api/v1/organisations/search")
async def search(
    q: str = Query("", max_length=100),
    period: str | None = None,
    sort: Literal["name", "attendances", "four_hour_pct"] = "attendances",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(25, ge=1, le=100),
):
    async with read_session() as conn:
        data = await ae_data(conn, params(period))
        rows = data["providers"]
        filtered = [
            r for r in rows if q.casefold() in (r["name"] + " " + r["code"]).casefold()
        ]
        filtered.sort(
            key=lambda r: (
                r[sort] is not None,
                r[sort] if r[sort] is not None else "" if sort == "name" else 0,
            ),
            reverse=direction == "desc",
        )
    return {
        "rows": filtered[(page - 1) * limit : page * limit],
        "total": len(filtered),
        "page": page,
        "reporting_period": data["period"],
    }


@app.get("/api/v1/organisations/detail/{code}")
async def organisation_detail(code: str, period: str | None = None):
    if not __import__("re").fullmatch("[A-Z0-9]{3,8}", code):
        raise HTTPException(422, "Invalid ODS code")
    p = params(period, provider=code)
    async with read_session() as conn:
        org = await fetch(
            conn,
            "SELECT * FROM ref.organisation WHERE code=:code ORDER BY valid_from DESC",
            {"code": code},
        )
        if not org:
            raise HTTPException(404, "Organisation not found")
        return {
            "organisation": org[0],
            "history": org,
            "ae": await ae_data(conn, p),
            "beds": await bed_data(conn, p),
            "diagnostics": await diagnostic_data(conn, p),
            "relationships": await fetch(
                conn,
                "SELECT * FROM ref.organisation_relationship WHERE provider_code=:code ORDER BY valid_from DESC",
                {"code": code},
            ),
        }


@app.get("/api/v1/organisations/compare")
async def compare(codes: str, period: str | None = None):
    items = codes.split(",")
    if not 1 <= len(items) <= 3 or any(
        not __import__("re").fullmatch("[A-Z0-9]{3,8}", x) for x in items
    ):
        raise HTTPException(422, "Choose one to three valid ODS codes")
    async with read_session() as conn:
        return [await ae_data(conn, params(period, provider=code)) for code in items]


@app.get("/api/v1/geographies/list")
async def geographies(kind: Literal["icb", "region"] = "region"):
    async with read_session() as conn:
        return await fetch(
            conn,
            f"SELECT code,name,valid_from,valid_to,source_url,licence FROM geo.{'icb_boundary' if kind == 'icb' else 'nhs_region_boundary'} ORDER BY name",
        )


@app.get("/api/v1/geographies/boundaries")
async def boundaries(
    kind: Literal["icb", "region"] = "region", period: str | None = None
):
    day = params(period)["period"] or date.today()
    async with read_session() as conn:
        rows = await fetch(
            conn,
            f"SELECT code,name,valid_from,source_url,licence,ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.001))::json AS geometry FROM geo.{'icb_boundary' if kind == 'icb' else 'nhs_region_boundary'} WHERE valid_from<=:day AND (valid_to IS NULL OR valid_to>:day)",
            {"day": day},
        )
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": r.pop("geometry"), "properties": r}
            for r in rows
        ],
    }


@app.get("/api/v1/geographies/metrics")
async def geographic_metrics(
    kind: Literal["icb", "region"] = "region",
    period: str | None = None,
    type: Literal["all", "type1", "type2", "other"] = "all",
):
    async with read_session() as conn:
        data = await ae_data(conn, params(period, type=type))
        if kind == "region":
            return data["regions"]
        return await fetch(
            conn,
            "SELECT rel.parent_code code,rel.parent_name name,sum(a.attendances) attendances,100.0*sum(a.attendances-a.over_four)/nullif(sum(a.attendances),0) four_hour_pct,count(*) providers FROM mart.ae a JOIN ref.organisation_relationship rel ON rel.provider_code=a.provider_code AND rel.relationship='ICB' AND rel.valid_from<=a.period AND (rel.valid_to IS NULL OR rel.valid_to>a.period) WHERE a.grain='provider' AND a.attendance_type=:type AND a.period=:period GROUP BY rel.parent_code,rel.parent_name ORDER BY four_hour_pct DESC",
            {"type": type, "period": data["period"]},
        )


@app.get("/api/v1/forecast/{view}")
async def forecast_endpoint(
    view: Literal["series", "backtests", "models"], horizon: int = Query(3, ge=1, le=12)
):
    async with read_session() as conn:
        models = await fetch(
            conn, "SELECT * FROM ml.model_version ORDER BY trained_through DESC"
        )
        if view == "models":
            return models
        if not models:
            return {
                "available": False,
                "reason": "Comparable history or evaluation coverage is insufficient.",
            }
        model = models[0]
        rows = await fetch(
            conn,
            "SELECT * FROM ml.forecast WHERE model_id=:id AND horizon<=:horizon ORDER BY period"
            if view == "series"
            else "SELECT * FROM ml.backtest WHERE model_id=:id ORDER BY origin,period",
            {"id": model["id"], "horizon": horizon},
        )
        return {"model": model, "rows": rows}


@app.get("/api/v1/export/{screen}")
async def export(
    screen: str,
    period: str | None = None,
    type: Literal["all", "type1", "type2", "other"] = "all",
    bed_type: Literal["overnight", "day"] = "overnight",
    region: str | None = Query(None, max_length=100),
    provider: str | None = Query(None, pattern="^[A-Z0-9]{3,8}$"),
    booked: Literal["include", "exclude"] = "include",
    diagnostic_grain: Literal["provider", "commissioner"] = "provider",
    horizon: int = Query(3, ge=1, le=12),
    q: str = Query("", max_length=100),
    icb: str | None = Query(None, pattern="^[A-Z0-9]{3,8}$"),
):
    if screen not in SCREENS:
        raise HTTPException(404, "Unknown screen")
    async with read_session() as conn:
        result = await workspace(
            conn,
            screen,
            params(
                period,
                region,
                provider,
                type,
                booked,
                bed_type,
                diagnostic_grain,
                horizon,
                icb,
            ),
        )
    rows = (
        result.get("forecast", [])
        if screen == "forecasting"
        else result["table"] or [r for c in result["charts"] for r in c["rows"]]
    )
    if q:
        rows = [
            r
            for r in rows
            if q.casefold()
            in (str(r.get("name", "")) + " " + str(r.get("code", ""))).casefold()
        ]
    provenance = json.dumps(jsonable_encoder(result["provenance"]))
    rows = [
        {
            **r,
            "selected_reporting_month": result["period"],
            "selected_quarter": result["quarter"],
            "release_provenance": provenance,
        }
        for r in rows
    ]
    fields = list(dict.fromkeys(k for row in rows for k in row))
    stream = io.StringIO()
    out = csv.DictWriter(stream, fieldnames=fields)
    out.writeheader()
    for row in rows:
        safe = {
            k: json.dumps(v, default=str)
            if isinstance(v, (dict, list))
            else (
                "'" + v
                if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                else v
            )
            for k, v in row.items()
        }
        out.writerow(safe)
    return Response(
        "\ufeff" + stream.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="nhs-pulse-{screen}.csv"'
        },
    )


class Investigation(BaseModel):
    model_config = {"extra": "forbid"}
    question: str = Field(min_length=5, max_length=1500)


@app.post("/api/v1/analyst/ask")
async def ask(body: Investigation, request: Request):
    from services.ai.analyst import investigate

    return await investigate(request.state.visitor, body.question.strip())


@app.get("/api/v1/analyst/conversations")
async def conversations(request: Request):
    async with read_session() as c:
        return await fetch(
            c,
            "SELECT id,question,status,created_at FROM ai.conversation WHERE session_id=:s ORDER BY created_at DESC LIMIT 30",
            {"s": request.state.visitor},
        )


@app.get("/api/v1/analyst/conversations/{identifier}")
async def conversation(identifier: UUID, request: Request):
    async with read_session() as c:
        rows = await fetch(
            c,
            "SELECT id,answer,status FROM ai.conversation WHERE id=:id AND session_id=:s",
            {"id": identifier, "s": request.state.visitor},
        )
        if not rows:
            raise HTTPException(404, "Investigation not found")
        return {
            **rows[0],
            "evidence": [
                r["payload"]
                for r in await fetch(
                    c,
                    "SELECT payload FROM ai.evidence WHERE conversation_id=:id ORDER BY id",
                    {"id": identifier},
                )
            ],
        }


@app.get("/api/v1/analyst/evidence/{identifier}")
async def evidence(identifier: UUID, request: Request):
    async with read_session() as c:
        rows = await fetch(
            c,
            "SELECT e.payload FROM ai.evidence e JOIN ai.conversation a ON a.id=e.conversation_id WHERE e.tool_call_id=:id AND a.session_id=:s",
            {"id": identifier, "s": request.state.visitor},
        )
        if not rows:
            raise HTTPException(404, "Evidence not found")
        return rows[0]["payload"]
