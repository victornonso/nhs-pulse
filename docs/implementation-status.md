# Verification record

This file records engineering acceptance, not claims about live NHS operations.

- PostgreSQL 18 and PostGIS 3.6.2 running locally in an isolated cluster.
- Immutable source storage, validation, atomic publication and revision lineage implemented.
- Official A&E, KH03 overnight/day and DM01 history ingested; exact coverage is available from publication metadata.
- Seven official NHS region geometries and 36 April 2026 ICB geometries loaded.
- Effective April 2026 provider/ICB mapping loaded; ODS legal metadata enrichment implemented.
- Twelve dbt models and four database data tests built successfully.
- Twenty Python tests pass, including isolated-database correction, no-change, quarantine and rollback acceptance.
- Eight SQL-backed FastAPI workspace routes pass smoke checks.
- Next.js production build and TypeScript validation pass.
- Seasonal benchmark and ETS rolling-origin evaluation completed on 36 monthly attendance observations; sparse forecast horizons withheld.
- DeepSeek configured locally with server-side quotas; live investigation verification in progress.
- Responsive browser captures and interaction checks in progress.
- Docker Compose and CI definitions implemented; runtime/deployment verification in progress.
- Public hosting and portfolio integration are not yet verified.
