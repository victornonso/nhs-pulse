"""Offline smoke dataset: captured, unmodified official releases with source lineage."""

import json
from pathlib import Path
from sqlalchemy import text
from apps.api.database import transaction
from pipelines.discovery.sources import SOURCES
from pipelines.orchestration.ingest import ingest_bytes
from tools.seed_sources import METRICS


def main():
    root = Path(__file__).resolve().parents[1]
    with transaction() as c:
        for key, s in SOURCES.items():
            c.execute(
                text(
                    "INSERT INTO ops.source(id,name,page_url,cadence,enabled) VALUES(:id,:n,:u,:c,:e) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": key,
                    "n": s["name"],
                    "u": s["page"],
                    "c": s["cadence"],
                    "e": s.get("enabled", True),
                },
            )
        for key, label, unit, definition, source, num, den in METRICS:
            c.execute(
                text(
                    "INSERT INTO ref.metric_definition(id,label,unit,definition,source_id,numerator,denominator) VALUES(:id,:l,:u,:d,:s,:n,:den) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": key,
                    "l": label,
                    "u": unit,
                    "d": definition,
                    "s": source,
                    "n": num,
                    "den": den,
                },
            )
    for source, name in [
        ("ae", "ae-september-2026.csv"),
        ("beds_overnight", "beds-q1-2026.xlsx"),
        ("diagnostics", "diagnostics-august-2026.zip"),
    ]:
        path = root / "tests/fixtures" / name
        meta = json.loads(
            path.with_suffix(path.suffix + ".json").read_text(encoding="utf-8")
        )
        print(ingest_bytes(source, meta["official_url"], name, path.read_bytes()))


if __name__ == "__main__":
    main()
