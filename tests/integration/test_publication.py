"""Correction fixtures are confined to nhs_pulse_test, never the application database."""

import os
import io
from pathlib import Path
import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from apps.api.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1",
    reason="Set RUN_DATABASE_TESTS=1 for isolated PostgreSQL acceptance",
)


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    url = make_url(settings.migration_database_url).set(database="nhs_pulse_test")
    admin = create_engine(
        make_url(settings.migration_database_url).set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as c:
        if not c.execute(
            text("SELECT 1 FROM pg_database WHERE datname='nhs_pulse_test'")
        ).scalar():
            c.execute(text("CREATE DATABASE nhs_pulse_test"))
    engine = create_engine(url)
    with engine.begin() as c:
        for path in sorted((Path(__file__).parents[2] / "db/sql").glob("*.sql")):
            if (
                not c.execute(text("SELECT to_regclass('ops.source')")).scalar()
                or path.name != "001_platform.sql"
            ):
                # Each migration is recorded so repeated acceptance runs preserve their audit history.
                c.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS public.test_migration(name text PRIMARY KEY)"
                    )
                )
                if not c.execute(
                    text("SELECT 1 FROM public.test_migration WHERE name=:n"),
                    {"n": path.name},
                ).scalar():
                    c.connection.driver_connection.execute(
                        path.read_text(encoding="utf-8")
                    )
                    c.execute(
                        text("INSERT INTO public.test_migration VALUES(:n)"),
                        {"n": path.name},
                    )
        c.execute(
            text(
                "INSERT INTO ops.source(id,name,page_url,cadence) VALUES('ae','Acceptance fixture','https://www.england.nhs.uk','monthly') ON CONFLICT DO NOTHING"
            )
        )
    from apps.api import database as module

    previous = module.writer
    storage = settings.raw_storage
    module.writer = engine
    settings.raw_storage = tmp_path_factory.mktemp("nhs_raw")
    yield engine
    module.writer = previous
    settings.raw_storage = storage
    engine.dispose()
    admin.dispose()


def test_release_nochange_revision_quarantine_rollback(database):
    from pipelines.orchestration import ingest

    ingest.writer = database
    body = (Path(__file__).parents[1] / "fixtures/ae-september-2026.csv").read_bytes()
    # A unique official-domain path isolates repeat runs while the content is a captured official file.
    from uuid import uuid4

    url = "https://www.england.nhs.uk/acceptance/" + str(uuid4()) + ".csv"
    first = ingest.ingest_bytes("ae", url, "September 2026", body)
    assert first["status"] in ("published", "revised")
    with database.connect() as c:
        before = c.execute(
            text(
                "SELECT generation FROM ops.mart_publication WHERE source_id='ae' AND reporting_period='2026-09-01'"
            )
        ).scalar()
    assert (
        ingest.ingest_bytes("ae", url, "September 2026", body)["status"] == "no-change"
    )
    with database.connect() as c:
        assert (
            c.execute(
                text(
                    "SELECT generation FROM ops.mart_publication WHERE source_id='ae' AND reporting_period='2026-09-01'"
                )
            ).scalar()
            == before
        )
    frame = pd.read_csv(io.BytesIO(body), dtype=str).fillna("")
    col = "A&E attendances Type 1"
    frame.loc[0, col] = str(int(frame.loc[0, col]) + 1)
    idx = frame["Org Code"].str.upper() == "TOTAL"
    frame.loc[idx, col] = str(int(frame.loc[idx, col].iloc[0]) + 1)
    corrected = frame.to_csv(index=False).encode()
    second = ingest.ingest_bytes("ae", url, "September 2026", corrected)
    assert second["status"] == "revised"
    with database.connect() as c:
        assert (
            str(
                c.execute(
                    text("SELECT revision_of FROM ops.release_version WHERE id=:id"),
                    {"id": second["release_id"]},
                ).scalar()
            )
            == first["release_id"]
        )
        assert (
            c.execute(
                text(
                    "SELECT attendances FROM mart.ae WHERE grain='national' AND attendance_type='all'"
                )
            ).scalar()
            == 2444744
        )
    invalid = ingest.ingest_bytes(
        "ae", url, "September 2026", corrected + b"\n", fault="invalid_denominator"
    )
    assert invalid["status"] == "quarantined"
    with pytest.raises(RuntimeError):
        ingest.ingest_bytes(
            "ae", url, "September 2026", corrected + b"\n\n", fault="publish_failure"
        )
    with database.connect() as c:
        assert (
            str(
                c.execute(
                    text(
                        "SELECT release_id FROM ops.mart_publication WHERE source_id='ae' AND reporting_period='2026-09-01'"
                    )
                ).scalar()
            )
            == second["release_id"]
        )
        assert (
            c.execute(
                text(
                    "SELECT count(*) FROM core.ae_monthly f JOIN ops.release_version r ON r.id=f.release_id WHERE r.status='failed'"
                )
            ).scalar()
            == 0
        )
    with pytest.raises(Exception):
        with database.begin() as c:
            c.execute(text("UPDATE raw.asset SET content='\\x01'"))
