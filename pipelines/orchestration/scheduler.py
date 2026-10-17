"""Persisted, calendar-aware collection; web visits never schedule ingestion."""

import logging
import json
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy import text
from apps.api.settings import settings
from apps.api.database import transaction
from .collect import collect

SOURCES = ("ae", "beds_overnight", "beds_day", "diagnostics")
log = logging.getLogger("nhs.collection")


def tick(corrections=False):
    for source in SOURCES:
        try:
            result = collect(source, backfill=3, corrections=corrections)
            log.info(
                json.dumps(
                    {"event": "source-check", "source": source, "result": result},
                    default=str,
                )
            )
        except Exception as exc:
            log.exception("Source collection failed: %s", source)
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


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    store = SQLAlchemyJobStore(
        url=settings.worker_database_url or settings.migration_database_url,
        tablename="scheduler_jobs",
        tableschema="ops",
    )
    scheduler = BlockingScheduler(
        jobstores={"default": store},
        timezone="Europe/London",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
    )
    scheduler.add_job(
        "pipelines.orchestration.scheduler:tick",
        "cron",
        minute="17",
        id="release-discovery",
        replace_existing=True,
    )
    scheduler.add_job(
        "pipelines.orchestration.scheduler:tick",
        "cron",
        day_of_week="sun",
        hour=4,
        minute=17,
        kwargs={"corrections": True},
        id="historical-revisions",
        replace_existing=True,
    )
    from pipelines.discovery.geography import load

    scheduler.add_job(
        load,
        "cron",
        day=1,
        hour=5,
        minute=17,
        id="official-geography",
        replace_existing=True,
    )
    scheduler.add_job(
        "pipelines.discovery.geography:enrich_ods",
        "cron",
        hour=4,
        minute=47,
        id="daily-ods-enrichment",
        replace_existing=True,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
