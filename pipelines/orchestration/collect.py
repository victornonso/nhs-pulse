import argparse
import json
import re
import time
from datetime import datetime, UTC, timedelta
import httpx
from sqlalchemy import text
from apps.api.database import transaction, records
from pipelines.discovery.sources import SOURCES, annual_page, fetch_page
from pipelines.adapters.nhs import month
from pipelines.orchestration.ingest import ingest_bytes


def due(source, now=None):
    now = now or datetime.now(UTC)
    with transaction() as conn:
        row = records(
            conn, "SELECT * FROM ops.source WHERE id=:source", {"source": source}
        )[0]
        if not row["enabled"]:
            return False
        last = row["last_checked"]
        events = records(
            conn,
            "SELECT expected_at FROM ops.publication_calendar WHERE source_id=:source AND expected_at BETWEEN :start AND :finish ORDER BY expected_at DESC LIMIT 1",
            {"source": source, "start": now - timedelta(hours=6), "finish": now},
        )
        interval = timedelta(hours=1 if events else 24)
        return last is None or now - last >= interval


def collect(source, backfill=1, force=False, corrections=False):
    if source not in ("ae", "beds_overnight", "beds_day", "diagnostics"):
        return {"source": source, "status": "metadata-managed"}
    if not force and not due(source):
        return {"source": source, "status": "scheduled"}
    now = datetime.now(UTC)
    fiscal = now.year - (now.month < 4)
    pages = (
        [SOURCES[source]["page"]]
        if source.startswith("beds")
        else [
            annual_page(source, y)
            for y in range(
                fiscal, fiscal - (4 if backfill > 24 else 3 if backfill > 6 else 2), -1
            )
        ]
    )
    assets = []
    with httpx.Client(
        timeout=90,
        follow_redirects=True,
        headers={
            "User-Agent": "NHS-Pulse/1.0 (public aggregate statistics; github.com/victornonso/nhs-pulse)"
        },
    ) as client:
        for page in pages:
            try:
                with transaction() as conn:
                    cached = records(
                        conn,
                        "SELECT * FROM ops.discovery_page WHERE source_id=:s AND url=:u",
                        {"s": source, "u": page},
                    )
                conditional = {}
                if cached and not force:
                    if cached[0]["etag"]:
                        conditional["If-None-Match"] = cached[0]["etag"]
                    if cached[0]["last_modified"]:
                        conditional["If-Modified-Since"] = cached[0]["last_modified"]
                response, found, description = fetch_page(
                    client, page, source, conditional
                )
                if response.status_code == 304:
                    found = cached[0]["assets"] if cached else []
                else:
                    with transaction() as conn:
                        conn.execute(
                            text(
                                "INSERT INTO ops.discovery_page(source_id,url,etag,last_modified,assets) VALUES(:s,:u,:e,:l,cast(:a as jsonb)) ON CONFLICT(source_id,url) DO UPDATE SET etag=excluded.etag,last_modified=excluded.last_modified,assets=excluded.assets,checked_at=now()"
                            ),
                            {
                                "s": source,
                                "u": page,
                                "e": response.headers.get("etag"),
                                "l": response.headers.get("last-modified"),
                                "a": json.dumps(found),
                            },
                        )
                assets.extend(found)
                with transaction() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO ops.discovery_check(source_id,status,http_status,etag,last_modified,asset_count) VALUES(:source,:status,:http,:etag,:lm,:count)"
                        ),
                        {
                            "source": source,
                            "status": "no-change"
                            if response.status_code == 304
                            else "discovered",
                            "http": response.status_code,
                            "etag": response.headers.get("etag"),
                            "lm": response.headers.get("last-modified"),
                            "count": len(found),
                        },
                    )
                    for a in found:
                        conn.execute(
                            text(
                                "INSERT INTO ops.source_asset(source_id,url,title) VALUES(:source,:url,:title) ON CONFLICT(source_id,url) DO UPDATE SET title=excluded.title"
                            ),
                            {"source": source, "url": a["url"], "title": a["title"]},
                        )
            except Exception as exc:
                with transaction() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO ops.discovery_check(source_id,status,message) VALUES(:source,'failed',:message)"
                        ),
                        {"source": source, "message": str(exc)[:500]},
                    )
                if not assets:
                    raise
            time.sleep(0.2)
        if source.startswith("beds"):

            def key(a):
                year = re.search(r"(20\d\d)[-/]\d\d", a["title"])
                q = re.search(r"Quarter\s+(\d)", a["title"])
                return int(year[1]) * 4 + int(q[1]) if year and q else 0
        else:

            def key(a):
                try:
                    return month(a["title"]).toordinal()
                except ValueError:
                    return 0

        unique = {}
        for a in assets:
            unique.setdefault(key(a) or a["url"], a)
        assets = sorted(unique.values(), key=key, reverse=True)[
            : 48 if corrections else backfill
        ]
        results = []
        for a in assets:
            with transaction() as conn:
                known = records(
                    conn,
                    "SELECT * FROM ops.source_asset WHERE source_id=:source AND url=:url",
                    {"source": source, "url": a["url"]},
                )
            headers = {}
            if known and not force:
                if known[0]["etag"]:
                    headers["If-None-Match"] = known[0]["etag"]
                if known[0]["last_modified"]:
                    headers["If-Modified-Since"] = known[0]["last_modified"]
            response = client.get(a["url"], headers=headers)
            if response.status_code == 304:
                with transaction() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO ops.discovery_check(source_id,status,http_status,message) VALUES(:source,'no-change',304,:message)"
                        ),
                        {"source": source, "message": a["url"]},
                    )
                results.append({"status": "no-change", "url": a["url"]})
                continue
            response.raise_for_status()
            published = None
            if a.get("companion"):
                from pipelines.discovery.publication import publication_evidence

                try:
                    published = publication_evidence(client, source, a["companion"])
                except (ValueError, AssertionError):
                    pass
            result = ingest_bytes(
                source,
                a["url"],
                a["title"],
                response.content,
                published,
                trigger="backfill" if backfill > 1 else "scheduled",
            )
            if published:
                with transaction() as conn:
                    conn.execute(
                        text(
                            "UPDATE ops.release_version SET published_at=coalesce(published_at,:p),metadata=metadata||cast(:m as jsonb) WHERE id=:id"
                        ),
                        {
                            "p": published,
                            "id": result["release_id"],
                            "m": json.dumps(
                                {
                                    "publication_precision": "date",
                                    "publication_evidence_url": a.get("companion"),
                                }
                            ),
                        },
                    )
            results.append(result)
            print(source, json.dumps(result), flush=True)
            with transaction() as conn:
                conn.execute(
                    text(
                        "UPDATE ops.source_asset SET etag=:etag,last_modified=:lm WHERE source_id=:source AND url=:url"
                    ),
                    {
                        "source": source,
                        "url": a["url"],
                        "etag": response.headers.get("etag"),
                        "lm": response.headers.get("last-modified"),
                    },
                )
            time.sleep(0.2)
        with transaction() as conn:
            status = (
                "no-change"
                if results and all(r["status"] == "no-change" for r in results)
                else "checked"
            )
            conn.execute(
                text(
                    "UPDATE ops.source SET last_checked=now(),status=CASE WHEN :status='no-change' THEN :status ELSE status END WHERE id=:source"
                ),
                {"source": source, "status": status},
            )
        return {"source": source, "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="all")
    parser.add_argument("--backfill", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for source in (
        ("ae", "beds_overnight", "beds_day", "diagnostics")
        if args.source == "all"
        else (args.source,)
    ):
        print(
            json.dumps(collect(source, args.backfill, args.force), default=str),
            flush=True,
        )


if __name__ == "__main__":
    main()
