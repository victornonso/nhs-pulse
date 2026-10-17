CREATE TABLE core.diagnostic_non_nhs_exclusion(
 release_id uuid REFERENCES ops.release_version,provider_code text,test text,
 activity numeric,waiting_list numeric,waiting_six numeric,waiting_thirteen numeric,
 waiting_bands jsonb NOT NULL,PRIMARY KEY(release_id,provider_code,test)
);
CREATE TRIGGER immutable_diagnostic_scope BEFORE UPDATE OR DELETE ON core.diagnostic_non_nhs_exclusion FOR EACH ROW EXECUTE FUNCTION raw.reject_mutation();
CREATE OR REPLACE VIEW mart.diagnostics AS
SELECT f.release_id,f.provider_code,f.commissioner_code,f.period,f.provider_name,f.commissioner_name,f.provider_parent,f.test,
 CASE WHEN e.release_id IS NULL THEN f.activity ELSE f.activity-e.activity END AS activity,
 CASE WHEN e.release_id IS NULL THEN f.waiting_list ELSE f.waiting_list-e.waiting_list END AS waiting_list,
 CASE WHEN e.release_id IS NULL THEN f.waiting_six ELSE f.waiting_six-e.waiting_six END AS waiting_six,
 CASE WHEN e.release_id IS NULL THEN f.waiting_thirteen ELSE f.waiting_thirteen-e.waiting_thirteen END AS waiting_thirteen,
 CASE WHEN e.release_id IS NULL THEN f.waiting_bands ELSE
 (SELECT jsonb_object_agg(b.key,CASE WHEN b.value='null'::jsonb OR e.waiting_bands->b.key='null'::jsonb THEN NULL ELSE (b.value::text)::numeric-coalesce((e.waiting_bands->>b.key)::numeric,0) END) FROM jsonb_each(f.waiting_bands) b) END AS waiting_bands,
 f.flags||'"NHS-commissioned activity; NONC excluded from this analytical scope"'::jsonb AS flags,
 f.grain,r.published_at AS official_publication,r.created_at AS ingested_at,r.official_url,r.version
FROM core.diagnostics_monthly f
JOIN ops.mart_publication p ON f.release_id=p.release_id
JOIN ops.release_version r ON r.id=f.release_id
LEFT JOIN core.diagnostic_non_nhs_exclusion e ON e.release_id=f.release_id AND e.provider_code=f.provider_code AND e.test=f.test AND f.grain='provider'
WHERE f.commissioner_code<>'NONC';
