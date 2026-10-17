"""Immutable SQL platform migrations, adopted by Alembic."""

from pathlib import Path
from alembic import op
from sqlalchemy import text

revision = "0001_platform"
down_revision = None


def upgrade():
    connection = op.get_bind()
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS public.schema_migration(name text PRIMARY KEY,applied_at timestamptz DEFAULT now())"
        )
    )
    for path in sorted((Path(__file__).resolve().parents[2] / "sql").glob("*.sql")):
        if connection.execute(
            text("SELECT 1 FROM public.schema_migration WHERE name=:n"),
            {"n": path.name},
        ).scalar():
            continue
        connection.connection.driver_connection.execute(
            path.read_text(encoding="utf-8")
        )
        connection.execute(
            text("INSERT INTO public.schema_migration(name) VALUES(:n)"),
            {"n": path.name},
        )


def downgrade():
    raise RuntimeError(
        "Release evidence cannot be destructively downgraded. Restore a tested database snapshot."
    )
