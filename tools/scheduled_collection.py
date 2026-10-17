"""Stateless hosted runner; database state survives ephemeral Actions jobs."""

from datetime import datetime, UTC, timedelta
from sqlalchemy import text
from apps.api.database import writer, transaction, records
from pipelines.orchestration.collect import collect
from pipelines.discovery.geography import enrich_ods, load


def metadata_due(source, marker, interval):
    with transaction() as c:
        last = c.execute(
            text(
                "SELECT max(checked_at) FROM ops.discovery_check WHERE source_id=:s AND message=:m AND status='completed'"
            ),
            {"s": source, "m": marker},
        ).scalar()
    return last is None or datetime.now(UTC) - last >= interval


def record(source, marker):
    with transaction() as c:
        c.execute(
            text(
                "INSERT INTO ops.discovery_check(source_id,status,message) VALUES(:s,'completed',:m)"
            ),
            {"s": source, "m": marker},
        )


def main():
    failures = []
    with writer.connect() as guard:
        if not guard.execute(text("SELECT pg_try_advisory_lock(76184201)")).scalar():
            print("Another collection runner holds the lease.")
            return
        try:
            for source in ("ae", "beds_overnight", "beds_day", "diagnostics"):
                try:
                    historical = metadata_due(
                        source, "historical-revision-audit", timedelta(days=7)
                    )
                    print(collect(source, backfill=3), flush=True)
                    if historical:
                        print(collect(source, force=True, corrections=True), flush=True)
                        record(source, "historical-revision-audit")
                except Exception as exc:
                    failures.append(source)
                    with transaction() as c:
                        c.execute(
                            text(
                                "UPDATE ops.source SET status='failed',last_checked=now() WHERE id=:s"
                            ),
                            {"s": source},
                        )
                        c.execute(
                            text(
                                "INSERT INTO ops.discovery_check(source_id,status,message) VALUES(:s,'failed',:m)"
                            ),
                            {"s": source, "m": str(exc)[:500]},
                        )
            for source, marker, interval, task in [
                ("ods", "ods-enrichment", timedelta(days=1), enrich_ods),
                ("boundaries", "geometry-refresh", timedelta(days=30), load),
            ]:
                try:
                    if metadata_due(source, marker, interval):
                        task()
                        record(source, marker)
                except Exception:
                    failures.append(marker)
            with transaction() as c:
                releases = {
                    r["release_id"]
                    for r in records(
                        c,
                        "SELECT release_id FROM ops.mart_publication WHERE source_id='ae'",
                    )
                }
                model = c.execute(
                    text(
                        "SELECT release_ids FROM ml.model_version WHERE metric='attendances' ORDER BY trained_through DESC,id DESC LIMIT 1"
                    )
                ).scalar()
            if releases and (not model or releases != set(model)):
                from services.forecasting.train import train

                print(train(), flush=True)
        finally:
            guard.execute(text("SELECT pg_advisory_unlock(76184201)"))
    if failures:
        raise RuntimeError("Scheduled tasks need attention: " + ", ".join(failures))


if __name__ == "__main__":
    main()
