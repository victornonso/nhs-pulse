"""Build the NONC exclusion dimension from immutable official raw matrix cells."""

from apps.api.database import transaction, records
from pipelines.adapters.nhs import diagnostics
from pipelines.orchestration.ingest import insert_rows


def main():
    with transaction() as c:
        rows = records(
            c,
            "SELECT r.id,r.reporting_period,a.content FROM ops.release_version r JOIN raw.asset a ON a.id=r.asset_id WHERE r.source_id='diagnostics' AND r.status='published' AND NOT EXISTS(SELECT 1 FROM core.diagnostic_non_nhs_exclusion e WHERE e.release_id=r.id)",
        )
    for r in rows:
        parsed = diagnostics(r["content"], str(r["reporting_period"]))
        if parsed.exclusions:
            with transaction() as c:
                insert_rows(
                    c, "core.diagnostic_non_nhs_exclusion", parsed.exclusions, r["id"]
                )
        print(r["reporting_period"], len(parsed.exclusions), flush=True)


if __name__ == "__main__":
    main()
