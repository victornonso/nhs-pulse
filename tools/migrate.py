"""Apply immutable platform migrations and isolate reader/writer responsibilities."""

import secrets
from sqlalchemy import create_engine, text
from apps.api.settings import settings, ROOT


def main():
    engine = create_engine(settings.migration_database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS public.schema_migration(name text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
            )
        )
        for path in sorted((ROOT / "db/sql").glob("*.sql")):
            if conn.execute(
                text("SELECT 1 FROM public.schema_migration WHERE name=:name"),
                {"name": path.name},
            ).scalar():
                continue
            conn.connection.driver_connection.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                text("INSERT INTO public.schema_migration(name) VALUES(:name)"),
                {"name": path.name},
            )
        for schema in ["raw", "ref", "core", "geo", "mart", "ml", "ai", "ops"]:
            conn.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO nhs_app"))
            conn.execute(
                text(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO nhs_app")
            )
        conn.execute(text("GRANT INSERT,UPDATE ON ALL TABLES IN SCHEMA ai TO nhs_app"))
        if not conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname='nhs_worker'")
        ).scalar():
            password = secrets.token_urlsafe(32)
            conn.execute(
                text(
                    f"CREATE ROLE nhs_worker LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE"
                )
            )
            from urllib.parse import urlparse

            parsed = urlparse(settings.migration_database_url)
            with (ROOT / ".env").open("a", encoding="utf-8") as out:
                out.write(
                    f"WORKER_DATABASE_URL=postgresql+psycopg://nhs_worker:{password}@{parsed.hostname}:{parsed.port}/nhs_pulse_db\n"
                )
        for schema in ["raw", "ref", "core", "geo", "mart", "ml", "ops"]:
            conn.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO nhs_worker"))
            conn.execute(
                text(
                    f"GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA {schema} TO nhs_worker"
                )
            )
            conn.execute(
                text(
                    f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO nhs_worker"
                )
            )
        conn.execute(text("GRANT DELETE ON ops.scheduler_jobs TO nhs_worker"))
        print(
            "Database migrations applied. PostGIS:",
            conn.execute(text("SELECT postgis_lib_version()")).scalar(),
        )


if __name__ == "__main__":
    main()
