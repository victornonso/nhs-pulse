"""Run dbt without persisting database credentials in profiles or shell history."""

import os
import subprocess
from urllib.parse import urlparse
from sqlalchemy import create_engine, text
from apps.api.settings import settings, ROOT


def main():
    with create_engine(settings.migration_database_url).begin() as c:
        c.execute(
            text("CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION nhs_worker")
        )
    u = urlparse(settings.worker_database_url or settings.migration_database_url)
    env = {
        **os.environ,
        "DBT_HOST": u.hostname,
        "DBT_PORT": str(u.port or 5432),
        "DBT_USER": u.username,
        "DBT_PASSWORD": u.password,
        "DBT_DATABASE": u.path.lstrip("/"),
    }
    subprocess.run(
        [
            "dbt",
            "build",
            "--project-dir",
            str(ROOT / "analytics/dbt"),
            "--profiles-dir",
            str(ROOT / "analytics/dbt"),
        ],
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
