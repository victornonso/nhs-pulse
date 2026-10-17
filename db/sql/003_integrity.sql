CREATE FUNCTION raw.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Published evidence is immutable. Insert a new release version.'; END;
$$;
CREATE TRIGGER immutable_asset BEFORE UPDATE OR DELETE ON raw.asset FOR EACH ROW EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_stage BEFORE UPDATE OR DELETE ON raw.staged_row FOR EACH ROW EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_ae BEFORE UPDATE OR DELETE ON core.ae_monthly FOR EACH ROW EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_beds BEFORE UPDATE OR DELETE ON core.bed_quarterly FOR EACH ROW EXECUTE FUNCTION raw.reject_mutation();
CREATE TRIGGER immutable_diagnostics BEFORE UPDATE OR DELETE ON core.diagnostics_monthly FOR EACH ROW EXECUTE FUNCTION raw.reject_mutation();
CREATE TABLE ops.discovery_page(source_id text REFERENCES ops.source,url text,etag text,last_modified text,assets jsonb NOT NULL,checked_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(source_id,url));
CREATE TABLE ops.scheduler_jobs(id varchar(191) PRIMARY KEY,next_run_time double precision,job_state bytea NOT NULL);
CREATE INDEX scheduler_next_run ON ops.scheduler_jobs(next_run_time);
CREATE VIEW mart.collection_status AS
 SELECT s.*,w.latest_period,
 (SELECT min(expected_at) FROM ops.publication_calendar WHERE source_id=s.id AND expected_at>now()) AS next_announced,
 CASE WHEN NOT s.enabled THEN 'Disabled'
 WHEN EXISTS(SELECT 1 FROM ops.ingestion_run r WHERE r.source_id=s.id AND r.status='failed' AND r.started_at>coalesce(s.last_ingested,'1900-01-01')) THEN 'Failed'
 WHEN EXISTS(SELECT 1 FROM ops.publication_calendar c WHERE c.source_id=s.id AND c.expected_at<now()-interval '72 hours' AND c.expected_at>now()-interval '90 days' AND c.reporting_period IS NOT NULL AND NOT EXISTS(SELECT 1 FROM ops.mart_publication p WHERE p.source_id=c.source_id AND p.reporting_period=c.reporting_period)) THEN 'Delayed'
 WHEN s.last_checked<now()-interval '26 hours' THEN 'Check overdue'
 WHEN s.status='no-change' THEN 'No new release'
 ELSE initcap(s.status) END AS collection_status
 FROM ops.source s LEFT JOIN ops.ingestion_watermark w ON w.source_id=s.id;
