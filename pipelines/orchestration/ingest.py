"""Immutable raw evidence, validated staging and atomic release publication."""

import hashlib
import json
import logging
from zoneinfo import ZoneInfo
from sqlalchemy import text
from apps.api.database import writer, transaction, records
from apps.api.settings import settings
from pipelines.adapters.nhs import parse
from pipelines.validation.checks import validate
from pipelines.discovery.sources import allowed_url

log = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")


def event(conn, run, state, detail=None):
    conn.execute(
        text(
            "INSERT INTO ops.pipeline_event(run_id,state,detail) VALUES(:run,:state,cast(:detail as jsonb))"
        ),
        {"run": run, "state": state, "detail": json.dumps(detail or {}, default=str)},
    )


def insert_rows(conn, table, rows, release):
    if table not in (
        "core.ae_monthly",
        "core.bed_quarterly",
        "core.diagnostics_monthly",
        "core.diagnostic_non_nhs_exclusion",
    ):
        raise ValueError("Unapproved staging table")
    columns = ["release_id", *rows[0].keys()]
    json_fields = {"flags", "waiting_bands"}
    values = [f"cast(:{c} as jsonb)" if c in json_fields else f":{c}" for c in columns]
    parameters = [
        {
            "release_id": release,
            **{
                k: json.dumps(v, default=str) if k in json_fields else v
                for k, v in r.items()
            },
        }
        for r in rows
    ]
    for start in range(0, len(parameters), 1000):
        conn.execute(
            text(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(values)})"
            ),
            parameters[start : start + 1000],
        )


def ingest_bytes(
    source,
    url,
    title,
    body,
    published_at=None,
    trigger="manual",
    fault=None,
    revalidate=False,
):
    if not allowed_url(url):
        raise ValueError("Only allowlisted official HTTPS assets may be ingested")
    if not body or len(body) > 150_000_000:
        raise ValueError("Asset size outside allowed bounds")
    sha = hashlib.sha256(body).hexdigest()
    with writer.connect() as lock:
        if not lock.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:source,0))"),
            {"source": source},
        ).scalar():
            return {"status": "busy", "source": source}
        with transaction() as conn:
            prior = records(
                conn,
                "SELECT r.* FROM ops.release_version r JOIN raw.asset a ON a.id=r.asset_id WHERE a.source_id=:source AND a.official_url=:url AND a.content_sha256=:sha",
                {"source": source, "url": url, "sha": sha},
            )
            run = conn.execute(
                text(
                    "INSERT INTO ops.ingestion_run(source_id,status,trigger) VALUES(:source,'downloaded',:trigger) RETURNING id"
                ),
                {"source": source, "trigger": trigger},
            ).scalar()
            if prior and not (
                revalidate and prior[0]["status"] in ("quarantined", "failed")
            ):
                status = (
                    "no-change"
                    if prior[0]["status"] in ("published", "superseded")
                    else "quarantined"
                )
                conn.execute(
                    text(
                        "UPDATE ops.ingestion_run SET status=:status,finished_at=now(),release_id=:release,message=:message WHERE id=:run"
                    ),
                    {
                        "status": status,
                        "release": prior[0]["id"],
                        "message": "Identical SHA256; published marts unchanged",
                        "run": run,
                    },
                )
                event(conn, run, status, {"sha256": sha})
                return {
                    "status": status,
                    "sha256": sha,
                    "release_id": str(prior[0]["id"]),
                    "run_id": str(run),
                }
            storage = settings.raw_storage / sha[:2] / sha
            storage.parent.mkdir(parents=True, exist_ok=True)
            if not storage.exists():
                with storage.open("xb") as out:
                    out.write(body)
            asset = conn.execute(
                text(
                    "INSERT INTO raw.asset(source_id,official_url,content_sha256,storage_uri,file_format,content) VALUES(:source,:url,:sha,:uri,:format,:content) ON CONFLICT DO NOTHING RETURNING id"
                ),
                {
                    "source": source,
                    "url": url,
                    "sha": sha,
                    "uri": str(storage.relative_to(settings.raw_storage)),
                    "format": url.split("?")[0].rsplit(".", 1)[-1],
                    "content": body,
                },
            ).scalar()
            if asset is None:
                asset = conn.execute(
                    text(
                        "SELECT id FROM raw.asset WHERE source_id=:s AND official_url=:u AND content_sha256=:h"
                    ),
                    {"s": source, "u": url, "h": sha},
                ).scalar()
            event(conn, run, "downloaded", {"sha256": sha, "bytes": len(body)})
        try:
            parsed = parse(source, body, title)
            if fault == "invalid_denominator":
                parsed.rows[0]["attendances"] = -1
            publication = parsed.publication or published_at
            if publication and publication.tzinfo is None:
                publication = publication.replace(tzinfo=LONDON)
            checks = validate(parsed)
            with transaction() as conn:
                current = records(
                    conn,
                    "SELECT r.* FROM ops.mart_publication p JOIN ops.release_version r ON r.id=p.release_id WHERE p.source_id=:source AND p.reporting_period=:period",
                    {"source": source, "period": parsed.period},
                )
                version = conn.execute(
                    text(
                        "SELECT coalesce(max(version),0)+1 FROM ops.release_version WHERE source_id=:source AND reporting_period=:period"
                    ),
                    {"source": source, "period": parsed.period},
                ).scalar()
                if prior:
                    release = prior[0]["id"]
                    conn.execute(
                        text(
                            "UPDATE ops.release_version SET status='validated',row_count=:rows WHERE id=:id"
                        ),
                        {"rows": len(parsed.rows), "id": release},
                    )
                else:
                    release = conn.execute(
                        text(
                            "INSERT INTO ops.release_version(source_id,asset_id,official_url,reporting_period,published_at,version,status,revision_of,row_count,metadata) VALUES(:source,:asset,:url,:period,:publication,:version,'validated',:previous,:rows,cast(:metadata as jsonb)) RETURNING id"
                        ),
                        {
                            "source": source,
                            "asset": asset,
                            "url": url,
                            "period": parsed.period,
                            "publication": publication,
                            "version": version,
                            "previous": current[0]["id"] if current else None,
                            "rows": len(parsed.rows),
                            "metadata": json.dumps(parsed.metadata),
                        },
                    ).scalar()
                conn.execute(
                    text(
                        "UPDATE ops.ingestion_run SET release_id=:release,row_count=:rows WHERE id=:run"
                    ),
                    {"release": release, "rows": len(parsed.rows), "run": run},
                )
                for c in checks:
                    conn.execute(
                        text(
                            "INSERT INTO ops.validation_result(release_id,run_id,check_name,passed,severity,detail) VALUES(:release,:run,:name,:passed,:severity,cast(:detail as jsonb))"
                        ),
                        {
                            "release": release,
                            "run": run,
                            **c,
                            "detail": json.dumps(c["detail"], default=str),
                        },
                    )
                if any(not c["passed"] and c["severity"] == "critical" for c in checks):
                    conn.execute(
                        text(
                            "UPDATE ops.release_version SET status='quarantined' WHERE id=:id"
                        ),
                        {"id": release},
                    )
                    conn.execute(
                        text(
                            "UPDATE ops.ingestion_run SET status='quarantined',finished_at=now(),message='Critical validation failed; previous mart retained' WHERE id=:id"
                        ),
                        {"id": run},
                    )
                    event(
                        conn,
                        run,
                        "quarantined",
                        {
                            "failed_checks": [
                                c["name"] for c in checks if not c["passed"]
                            ]
                        },
                    )
                    return {
                        "status": "quarantined",
                        "release_id": str(release),
                        "run_id": str(run),
                        "sha256": sha,
                    }
                event(conn, run, "validated", {"checks": len(checks)})
            with transaction() as conn:
                orgs = {}
                for r in parsed.rows:
                    code = r["provider_code"]
                    if code not in ("ALL", "ENGLAND"):
                        name = r.get("name", r.get("provider_name", code))
                        orgs[code] = name
                    commissioner = r.get("commissioner_code")
                    if commissioner and commissioner != "ALL":
                        orgs[commissioner] = r["commissioner_name"]
                for code, name in orgs.items():
                    conn.execute(
                        text(
                            "INSERT INTO ref.organisation(code,name,org_type,valid_from,status) VALUES(:code,:name,:kind,:period,'Published') ON CONFLICT(code,valid_from) DO UPDATE SET name=excluded.name"
                        ),
                        {
                            "code": code,
                            "name": name,
                            "kind": "ICB / Commissioner"
                            if "ICB" in name or "INTEGRATED CARE" in name
                            else "NHS Trust"
                            if "NHS" in name and "TRUST" in name
                            else "Provider",
                            "period": parsed.period,
                        },
                    )
                insert_rows(conn, parsed.table, parsed.rows, release)
                if parsed.exclusions:
                    insert_rows(
                        conn,
                        "core.diagnostic_non_nhs_exclusion",
                        parsed.exclusions,
                        release,
                    )
                # Staging retains normalised values and an exact link to the immutable original.
                for start in range(0, len(parsed.rows), 1000):
                    conn.execute(
                        text(
                            "INSERT INTO raw.staged_row(release_id,row_number,source_location,payload) VALUES(:release,:row,:location,cast(:payload as jsonb))"
                        ),
                        [
                            {
                                "release": release,
                                "row": i + start,
                                "location": title,
                                "payload": json.dumps(row, default=str),
                            }
                            for i, row in enumerate(parsed.rows[start : start + 1000])
                        ],
                    )
                event(conn, run, "staged", {"rows": len(parsed.rows)})
                event(conn, run, "reconciled")
                if fault == "publish_failure":
                    raise RuntimeError("Injected acceptance-test publication failure")
                if current:
                    conn.execute(
                        text(
                            "UPDATE ops.release_version SET status='superseded' WHERE id=:id"
                        ),
                        {"id": current[0]["id"]},
                    )
                conn.execute(
                    text(
                        "UPDATE ops.release_version SET status='published' WHERE id=:id"
                    ),
                    {"id": release},
                )
                conn.execute(
                    text(
                        "INSERT INTO ops.mart_publication(source_id,reporting_period,release_id) VALUES(:source,:period,:release) ON CONFLICT(source_id,reporting_period) DO UPDATE SET release_id=excluded.release_id,published_at=now(),generation=ops.mart_publication.generation+1"
                    ),
                    {"source": source, "period": parsed.period, "release": release},
                )
                status = "revised" if current else "published"
                conn.execute(
                    text(
                        "UPDATE ops.ingestion_run SET status=:status,finished_at=now() WHERE id=:run"
                    ),
                    {"status": status, "run": run},
                )
                conn.execute(
                    text(
                        "UPDATE ops.source SET last_ingested=now(),status=:status WHERE id=:source"
                    ),
                    {"status": status, "source": source},
                )
                conn.execute(
                    text(
                        "INSERT INTO ops.ingestion_watermark(source_id,latest_period,last_success) VALUES(:source,:period,now()) ON CONFLICT(source_id) DO UPDATE SET latest_period=greatest(ops.ingestion_watermark.latest_period,excluded.latest_period),last_success=now()"
                    ),
                    {"source": source, "period": parsed.period},
                )
                event(conn, run, "atomic-publish", {"version": version})
                event(conn, run, "cache-invalidation", {"release_id": str(release)})
                conn.execute(
                    text("SELECT pg_notify('nhs_mart_published',:id)"),
                    {"id": str(release)},
                )
            return {
                "status": status,
                "period": str(parsed.period),
                "rows": len(parsed.rows),
                "release_id": str(release),
                "run_id": str(run),
                "sha256": sha,
            }
        except Exception as exc:
            with transaction() as conn:
                conn.execute(
                    text(
                        "UPDATE ops.ingestion_run SET status='failed',finished_at=now(),message=:message WHERE id=:run"
                    ),
                    {"message": str(exc)[:1000], "run": run},
                )
                conn.execute(
                    text(
                        "UPDATE ops.release_version SET status='failed' WHERE asset_id=:asset AND status!='published'"
                    ),
                    {"asset": asset},
                )
                event(conn, run, "failed", {"message": str(exc)[:500]})
            raise
