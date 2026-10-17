# Operating NHS Pulse

The application reader has SELECT access to analytical evidence and INSERT/UPDATE only within its visitor-scoped AI tables. The worker writes pipeline and model records; migrations use a separate administrator connection. Database triggers reject mutation of original raw assets, staging rows and analytical facts.

## Collection

`python -m pipelines.orchestration.scheduler` runs persisted APScheduler jobs in PostgreSQL. Hourly ticks perform source-specific due checks. Sunday checks inspect older listed assets; a monthly metadata job refreshes official geography. The GitHub workflow provides a free-hosting execution option without keeping a worker service awake.

Page and asset ETag/Last-Modified headers are used where supported. The file SHA-256 is authoritative for unchanged content. A source-scoped PostgreSQL advisory lock prevents duplicate ingestion. The operations view distinguishes a successful discovery from a new publication. A 72-hour publication grace period avoids announcing a late release immediately at the expected minute.

The hosted entry point is `python -m tools.scheduled_collection`. GitHub Actions invokes it hourly; PostgreSQL records successful maintenance timestamps so ephemeral runners do not repeat weekly or monthly work on every run. A runner lease prevents overlap. Historical audits revisit published reporting periods rather than expanding the backfill implicitly. Discovery uses the official NHS public CMS API and checks canonical URLs before parsing file links. Failures remain visible and fail the workflow instead of advancing successful-maintenance timestamps.

## Failure and recovery

Inspect `/operations`, `/api/v1/operations/runs` and worker logs. A quarantined release has failed a critical contract check; its validation records explain why. The previously published version remains available. Do not edit raw files or force an invalid version into published marts. After inspecting a changed source contract, revalidate retained original evidence through the ingestion function's explicit `revalidate=True` path. The audit retains previous failed attempts.

For repeated network failures, inspect the official publication page and actual source availability before retrying. Do not change last-success timestamps by hand. Browser reload reads analytical views only. Administrator discovery is a separate authenticated action.

## Storage

Retain PostgreSQL backups and raw object storage. The database also stores immutable source bytes so a lost local raw directory does not destroy provenance. Monitor free disk space before large backfills and maintain at least several GB of working capacity. Docker volumes persist database/raw storage independently of containers.

## AI

Set a server-side provider key and a supported model in the ignored environment or hosting secret manager. The API uses nine allowlisted tools, bounded inputs and parameterised queries. No provider-supplied SQL is executed. Two requests per visitor per minute, six per day and forty globally per day constrain demo use. Changing browser sessions can evade visitor limits; the shared server-side budget remains the final cap. Review provider billing separately.

Conversation/history/evidence reads check the signed visitor identity. Shared data operations require the administrator key. Cross-origin mutation is rejected. Logs never print provider keys or database connection strings.
