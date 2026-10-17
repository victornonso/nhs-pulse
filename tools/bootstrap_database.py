"""Provision an isolated PostgreSQL 18 cluster on Windows; never use another project's DB."""

import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
LOCAL.mkdir(exist_ok=True)
BIN = Path(os.environ.get("POSTGRES_BIN", str(ROOT / ".local/pgsql/bin")))
PORT = "5546"
data = LOCAL / "pgdata"
envfile = ROOT / ".env"
if not envfile.exists():
    password = secrets.token_urlsafe(32)
    app_password = secrets.token_urlsafe(32)
    envfile.write_text(
        f"MIGRATION_DATABASE_URL=postgresql+psycopg://nhs_admin:{password}@127.0.0.1:{PORT}/nhs_pulse_db\nDATABASE_URL=postgresql+psycopg://nhs_app:{app_password}@127.0.0.1:{PORT}/nhs_pulse_db\nSESSION_SECRET={secrets.token_urlsafe(48)}\nAPP_ORIGIN=http://127.0.0.1:3020\nADMIN_KEY={secrets.token_urlsafe(32)}\n",
        encoding="utf-8",
    )
else:
    from urllib.parse import urlparse

    line = next(
        x
        for x in envfile.read_text().splitlines()
        if x.startswith("MIGRATION_DATABASE_URL=")
    )
    password = urlparse(line.split("=", 1)[1]).password
    app_password = urlparse(
        next(
            x.split("=", 1)[1]
            for x in envfile.read_text().splitlines()
            if x.startswith("DATABASE_URL=")
        )
    ).password
pwdfile = LOCAL / "init-password"
if not (data / "PG_VERSION").exists():
    pwdfile.write_text(password, encoding="utf-8")
    try:
        subprocess.run(
            [
                str(BIN / "initdb.exe"),
                "-D",
                str(data),
                "-U",
                "nhs_admin",
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--pwfile",
                str(pwdfile),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        pwdfile.unlink(missing_ok=True)
result = subprocess.run(
    [str(BIN / "pg_ctl.exe"), "-D", str(data), "status"],
    check=False,
    capture_output=True,
)
if result.returncode:
    subprocess.run(
        [
            str(BIN / "pg_ctl.exe"),
            "-D",
            str(data),
            "-l",
            str(LOCAL / "postgres.log"),
            "-o",
            f"-p {PORT} -h 127.0.0.1",
            "start",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
os.environ["PGPASSWORD"] = password
psql = [
    str(BIN / "psql.exe"),
    "-h",
    "127.0.0.1",
    "-p",
    PORT,
    "-U",
    "nhs_admin",
    "-d",
    "postgres",
    "-v",
    "ON_ERROR_STOP=1",
]
exists = subprocess.run(
    psql + ["-Atc", "SELECT 1 FROM pg_database WHERE datname='nhs_pulse_db'"],
    capture_output=True,
    text=True,
    check=True,
)
if not exists.stdout.strip():
    subprocess.run(
        psql + ["-c", "CREATE DATABASE nhs_pulse_db"], capture_output=True, check=True
    )
exists = subprocess.run(
    psql + ["-Atc", "SELECT 1 FROM pg_roles WHERE rolname='nhs_app'"],
    capture_output=True,
    text=True,
    check=True,
)
if not exists.stdout.strip():
    subprocess.run(
        psql
        + [
            "-c",
            f"CREATE ROLE nhs_app LOGIN PASSWORD '{app_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE",
        ],
        capture_output=True,
        check=True,
    )
print(
    "Isolated PostgreSQL 18 is ready: nhs_pulse_db on port 5546. Credentials remain in ignored .env."
)
