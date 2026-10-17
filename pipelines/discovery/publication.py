"""Read actual publication statements; calendar expectations never prove publication."""

import hashlib
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text
import xlrd
import openpyxl
from apps.api.database import transaction
from apps.api.settings import settings
from .sources import allowed_url


def publication_evidence(client, source, url):
    if not allowed_url(url):
        raise ValueError("Unapproved publication companion")
    response = client.get(url)
    response.raise_for_status()
    body = response.content
    if len(body) > 30_000_000:
        raise ValueError("Publication companion exceeds size bound")
    sha = hashlib.sha256(body).hexdigest()
    path = settings.raw_storage / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(body)
    with transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO raw.asset(source_id,official_url,content_sha256,storage_uri,file_format,content) VALUES(:s,:u,:sha,:path,:fmt,:b) ON CONFLICT DO NOTHING"
            ),
            {
                "s": source,
                "u": url,
                "sha": sha,
                "path": str(path.relative_to(settings.raw_storage)),
                "fmt": url.rsplit(".", 1)[-1],
                "b": body,
            },
        )
    if body[:2] == b"PK":
        workbook = openpyxl.load_workbook(
            io.BytesIO(body), read_only=True, data_only=True
        )
        rows = (
            r
            for sheet in workbook
            for r in sheet.iter_rows(max_row=20, values_only=True)
        )
    else:
        workbook = xlrd.open_workbook(file_contents=body)
        rows = (
            sheet.row_values(i)
            for sheet in workbook.sheets()
            for i in range(min(20, sheet.nrows))
        )
    for row in rows:
        line = " ".join(str(v) for v in row if v is not None)
        match = re.search(
            r"Publish(?:ed|ing|cation)?\s*(?:Date)?\s*:?\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",
            line,
            re.I,
        )
        if match:
            day = datetime.strptime(" ".join(match.groups()), "%d %B %Y").replace(
                tzinfo=ZoneInfo("Europe/London")
            )
            # Midnight is a storage convention for date-only source evidence, not an asserted release time.
            return day
    return None
