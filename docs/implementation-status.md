# Verification record

Verified 17 October 2026 against the running application and hosted database.

- Public application: https://nhs-pulse-victor-okeke.vercel.app/
- Public source: https://github.com/victornonso/nhs-pulse
- Hosted readiness: HTTP 200; PostgreSQL 18, PostGIS 3.6.4 and 56 analytical publications.
- 36 A&E months: October 2023–September 2026; 28,576 retained normalized fact rows.
- 12 diagnostics releases between March 2025 and August 2026; not an uninterrupted monthly series. 101,430 fact rows.
- Four overnight and four day-only KH03 quarters: July 2025–June 2026. 121,476 fact rows.
- Seven official NHS region geometries and 36 April 2026 ICB geometries; effective provider mapping.
- Immutable evidence, validation, atomic publication, no-change detection, revision lineage, quarantine and rollback acceptance executed.
- Twelve dbt models and four database data tests built successfully.
- Python acceptance covers official file contracts, missingness, calendar exceptions, database revision/rollback, immutable evidence, bounded tools, cache privacy and forecast comparability.
- All eight hosted SQL-backed workspace routes return HTTP 200.
- Genuine hosted DeepSeek investigation returns the September 2026 attendance total with release-linked evidence. Visitor and shared budgets persist in PostgreSQL.
- Next.js production build and TypeScript validation pass.
- Seasonal-naive versus damped ETS rolling-origin evaluation on 36 observations. ETS MAE 49,452.14; WAPE 2.09%. Horizons 1–7 have at least six calibration errors; longer horizons withheld.
- 24 actual captures retained in .local/screenshots: eight routes at 1440/768/390 pixels, with explicit viewport and overflow checks.
- Browser acceptance passes search, provider drill-down, keyboard dismissal and CSV download at all three widths.
- Complete Docker Compose stack verified in GitHub Actions, including official fixture ingestion and the frontend/API connection.
- Native local PostgreSQL/PostGIS, API, web and persisted scheduler verified. The Windows Docker Linux engine was unavailable; Compose execution was verified on the isolated Linux CI runner instead.
- Temporary Neon CLI OAuth token revoked. Runtime roles are scoped to reader and worker responsibilities; credentials excluded from source and browser code.

Current Actions results and screenshot artifacts are authoritative for subsequent commits. Source availability and collection outcomes are recorded independently of observation dates.
