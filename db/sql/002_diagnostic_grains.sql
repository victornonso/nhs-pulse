ALTER TABLE core.diagnostics_monthly ADD COLUMN grain text NOT NULL DEFAULT 'provider' CHECK(grain IN ('provider','commissioner'));
DROP VIEW mart.diagnostics;
CREATE VIEW mart.diagnostics AS SELECT f.*,r.published_at AS official_publication,r.created_at AS ingested_at,r.official_url,r.version FROM core.diagnostics_monthly f JOIN ops.mart_publication p ON f.release_id=p.release_id JOIN ops.release_version r ON r.id=f.release_id;
