CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS ml;
CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE ops.source (
 id text PRIMARY KEY, name text NOT NULL, page_url text NOT NULL,
 cadence text NOT NULL CHECK(cadence IN ('monthly','quarterly','daily','metadata','seasonal')),
 enabled boolean NOT NULL DEFAULT true, licence text NOT NULL DEFAULT 'Open Government Licence v3.0',
 policy jsonb NOT NULL DEFAULT '{}', last_checked timestamptz, last_ingested timestamptz,
 status text NOT NULL DEFAULT 'scheduled', metadata jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE ops.publication_calendar (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, source_id text NOT NULL REFERENCES ops.source,
 reporting_period date, expected_at timestamptz NOT NULL, official_url text NOT NULL,
 retrieved_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_id,expected_at)
);
CREATE TABLE ops.discovery_check (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id text NOT NULL REFERENCES ops.source,
 checked_at timestamptz NOT NULL DEFAULT now(), status text NOT NULL, http_status int,
 etag text,last_modified text,asset_count int NOT NULL DEFAULT 0,message text
);
CREATE TABLE ops.source_asset (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id text NOT NULL REFERENCES ops.source,
 url text NOT NULL, title text NOT NULL, discovered_at timestamptz NOT NULL DEFAULT now(),
 etag text,last_modified text, UNIQUE(source_id,url)
);
CREATE TABLE raw.asset (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id text NOT NULL REFERENCES ops.source,
 official_url text NOT NULL, content_sha256 text NOT NULL CHECK(length(content_sha256)=64),
 storage_uri text NOT NULL, acquired_utc timestamptz NOT NULL DEFAULT now(),
 file_format text NOT NULL, content bytea NOT NULL, UNIQUE(source_id,official_url,content_sha256)
);
CREATE TABLE ops.release_version (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id text NOT NULL REFERENCES ops.source,
 asset_id uuid NOT NULL REFERENCES raw.asset, official_url text NOT NULL,
 reporting_period date NOT NULL, published_at timestamptz,
 version int NOT NULL, status text NOT NULL, revision_of uuid REFERENCES ops.release_version,
 created_at timestamptz NOT NULL DEFAULT now(), row_count int NOT NULL DEFAULT 0,
 metadata jsonb NOT NULL DEFAULT '{}', UNIQUE(source_id,reporting_period,version), UNIQUE(asset_id)
);
CREATE TABLE raw.staged_row (
 release_id uuid NOT NULL REFERENCES ops.release_version, row_number int NOT NULL,
 source_location text NOT NULL, payload jsonb NOT NULL, PRIMARY KEY(release_id,row_number)
);
CREATE TABLE ops.ingestion_run (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id text NOT NULL REFERENCES ops.source,
 release_id uuid REFERENCES ops.release_version, started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,status text NOT NULL,row_count int NOT NULL DEFAULT 0,
 message text,trigger text NOT NULL DEFAULT 'scheduled'
);
CREATE TABLE ops.ingestion_watermark (
 source_id text PRIMARY KEY REFERENCES ops.source, latest_period date,
 last_success timestamptz, next_check timestamptz, etag text,last_modified text
);
CREATE TABLE ops.validation_result (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, release_id uuid REFERENCES ops.release_version,
 run_id uuid REFERENCES ops.ingestion_run, check_name text NOT NULL, passed boolean NOT NULL,
 severity text NOT NULL, detail jsonb NOT NULL DEFAULT '{}', checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ops.pipeline_event (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,run_id uuid NOT NULL REFERENCES ops.ingestion_run,
 state text NOT NULL,at timestamptz NOT NULL DEFAULT now(),detail jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE ops.mart_publication (
 source_id text NOT NULL REFERENCES ops.source,reporting_period date NOT NULL,
 release_id uuid NOT NULL REFERENCES ops.release_version,published_at timestamptz NOT NULL DEFAULT now(),
 generation bigint NOT NULL DEFAULT 1,PRIMARY KEY(source_id,reporting_period)
);
CREATE TABLE ref.organisation (
 code text NOT NULL,name text NOT NULL,org_type text NOT NULL DEFAULT 'Provider',
 valid_from date NOT NULL DEFAULT '1900-01-01',valid_to date,status text NOT NULL DEFAULT 'Unverified',
 ods jsonb NOT NULL DEFAULT '{}',PRIMARY KEY(code,valid_from),CHECK(valid_to IS NULL OR valid_to>valid_from)
);
CREATE TABLE ref.organisation_relationship (
 provider_code text NOT NULL,parent_code text NOT NULL,parent_name text NOT NULL,
 relationship text NOT NULL,valid_from date NOT NULL,valid_to date,official_url text NOT NULL,
 PRIMARY KEY(provider_code,parent_code,relationship,valid_from),CHECK(valid_to IS NULL OR valid_to>valid_from)
);
CREATE TABLE ref.calendar(day date PRIMARY KEY,month date NOT NULL,quarter date NOT NULL,days_in_quarter int NOT NULL);
CREATE TABLE ref.metric_definition(id text PRIMARY KEY,label text NOT NULL,unit text NOT NULL,definition text NOT NULL,source_id text REFERENCES ops.source,numerator text,denominator text,methodology jsonb NOT NULL DEFAULT '{}');
CREATE TABLE ref.source_methodology(source_id text PRIMARY KEY REFERENCES ops.source,notes jsonb NOT NULL,official_url text NOT NULL);

CREATE TABLE core.ae_monthly (
 release_id uuid NOT NULL REFERENCES ops.release_version,provider_code text NOT NULL,
 period date NOT NULL,name text NOT NULL,region text,grain text NOT NULL CHECK(grain IN ('provider','national')),
 attendance_type text NOT NULL CHECK(attendance_type IN ('type1','type2','other','all')),
 attendances numeric,over_four numeric,booked numeric,booked_over_four numeric,
 admissions numeric,other_admissions numeric,wait_4_12 numeric,wait_12_plus numeric,
 flags jsonb NOT NULL DEFAULT '[]',PRIMARY KEY(release_id,provider_code,attendance_type),
 CHECK(attendances IS NULL OR attendances>=0),CHECK(over_four IS NULL OR over_four>=0)
);
CREATE TABLE core.bed_quarterly (
 release_id uuid NOT NULL REFERENCES ops.release_version,provider_code text NOT NULL,
 quarter date NOT NULL,name text NOT NULL,region text,grain text NOT NULL,
 bed_type text NOT NULL CHECK(bed_type IN ('overnight','day')),specialty text NOT NULL,
 available_average numeric,occupied_average numeric,available_bed_days numeric,occupied_bed_days numeric,
 days_in_quarter int NOT NULL,flags jsonb NOT NULL DEFAULT '[]',
 PRIMARY KEY(release_id,provider_code,specialty),CHECK(days_in_quarter BETWEEN 90 AND 92)
);
CREATE TABLE core.diagnostics_monthly (
 release_id uuid NOT NULL REFERENCES ops.release_version,provider_code text NOT NULL,
 commissioner_code text NOT NULL,period date NOT NULL,provider_name text NOT NULL,
 commissioner_name text NOT NULL,provider_parent text,test text NOT NULL,
 activity numeric,waiting_list numeric,waiting_six numeric,waiting_thirteen numeric,
 waiting_bands jsonb NOT NULL DEFAULT '{}',flags jsonb NOT NULL DEFAULT '[]',
 PRIMARY KEY(release_id,provider_code,commissioner_code,test)
);
CREATE TABLE core.uec_observation (
 release_id uuid REFERENCES ops.release_version,organisation text,observed_at date,metric text,value numeric,
 PRIMARY KEY(release_id,organisation,observed_at,metric)
);
CREATE INDEX ae_period_provider ON core.ae_monthly(period,provider_code,attendance_type);
CREATE INDEX beds_period_provider ON core.bed_quarterly(quarter,provider_code,bed_type);
CREATE INDEX diagnostics_period_provider ON core.diagnostics_monthly(period,provider_code,test);
CREATE INDEX diagnostics_commissioner ON core.diagnostics_monthly(commissioner_code,period);
CREATE INDEX release_source_period ON ops.release_version(source_id,reporting_period,created_at);
CREATE INDEX run_source_started ON ops.ingestion_run(source_id,started_at DESC);

CREATE TABLE geo.icb_boundary(code text NOT NULL,name text NOT NULL,valid_from date NOT NULL,valid_to date,geom geometry(MultiPolygon,4326) NOT NULL,source_url text NOT NULL,licence text NOT NULL,PRIMARY KEY(code,valid_from));
CREATE TABLE geo.nhs_region_boundary(LIKE geo.icb_boundary INCLUDING ALL);
CREATE TABLE geo.provider_location(code text PRIMARY KEY,location geometry(Point,4326),location_type text NOT NULL DEFAULT 'Headquarters',source_url text NOT NULL);
CREATE INDEX icb_geometry ON geo.icb_boundary USING gist(geom);
CREATE INDEX region_geometry ON geo.nhs_region_boundary USING gist(geom);

CREATE TABLE ml.training_run(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),metric text NOT NULL,status text NOT NULL,metadata jsonb NOT NULL);
CREATE TABLE ml.model_version(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),training_id uuid REFERENCES ml.training_run,name text NOT NULL,metric text NOT NULL,release_ids uuid[] NOT NULL,trained_through date NOT NULL,metrics jsonb NOT NULL,metadata jsonb NOT NULL);
CREATE TABLE ml.forecast(model_id uuid REFERENCES ml.model_version,period date,horizon int,estimate numeric,lower_bound numeric,upper_bound numeric,PRIMARY KEY(model_id,period));
CREATE TABLE ml.backtest(model_id uuid REFERENCES ml.model_version,origin date,period date,actual numeric,predicted numeric,candidate text,PRIMARY KEY(model_id,origin,period,candidate));
CREATE TABLE ai.conversation(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),session_id text NOT NULL,question text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),status text NOT NULL,answer text,metadata jsonb NOT NULL DEFAULT '{}');
CREATE INDEX ai_session_time ON ai.conversation(session_id,created_at DESC);
CREATE TABLE ai.tool_call(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),conversation_id uuid NOT NULL REFERENCES ai.conversation,tool text NOT NULL,arguments jsonb NOT NULL,result jsonb NOT NULL,at timestamptz NOT NULL DEFAULT now());
CREATE TABLE ai.evidence(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),conversation_id uuid NOT NULL REFERENCES ai.conversation,tool_call_id uuid NOT NULL REFERENCES ai.tool_call,source_release_ids uuid[] NOT NULL DEFAULT '{}',payload jsonb NOT NULL);

CREATE VIEW mart.ae AS SELECT f.*,r.published_at AS official_publication,r.created_at AS ingested_at,r.official_url,r.version FROM core.ae_monthly f JOIN ops.mart_publication p ON f.release_id=p.release_id JOIN ops.release_version r ON r.id=f.release_id;
CREATE VIEW mart.beds AS SELECT f.*,r.published_at AS official_publication,r.created_at AS ingested_at,r.official_url,r.version FROM core.bed_quarterly f JOIN ops.mart_publication p ON f.release_id=p.release_id JOIN ops.release_version r ON r.id=f.release_id;
CREATE VIEW mart.diagnostics AS SELECT f.*,r.published_at AS official_publication,r.created_at AS ingested_at,r.official_url,r.version FROM core.diagnostics_monthly f JOIN ops.mart_publication p ON f.release_id=p.release_id JOIN ops.release_version r ON r.id=f.release_id;
CREATE VIEW mart.national_overview AS SELECT period,attendance_type,attendances,(attendances-over_four)*100.0/nullif(attendances,0) AS four_hour_pct,admissions+other_admissions AS emergency_admissions,wait_12_plus,release_id,official_publication,ingested_at,official_url,version FROM mart.ae WHERE grain='national';
CREATE VIEW mart.trend_seasonality AS SELECT *,attendances-lag(attendances) OVER(PARTITION BY attendance_type ORDER BY period) AS period_change,avg(attendances) OVER(PARTITION BY attendance_type ORDER BY period ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS trailing_average FROM mart.national_overview;
CREATE VIEW mart.source_freshness AS SELECT s.*,w.latest_period,w.next_check,(SELECT min(expected_at) FROM ops.publication_calendar c WHERE c.source_id=s.id AND c.expected_at>now()) AS next_announced FROM ops.source s LEFT JOIN ops.ingestion_watermark w ON w.source_id=s.id;
CREATE VIEW mart.trust_profile AS SELECT provider_code,name,period,attendance_type,attendances,over_four,(attendances-over_four)*100.0/nullif(attendances,0) AS four_hour_pct,region,flags,release_id FROM mart.ae WHERE grain='provider';
CREATE VIEW mart.geography_comparison AS SELECT period,region,attendance_type,sum(attendances) attendances,sum(admissions+other_admissions) admissions,100.0*sum(attendances-over_four)/nullif(sum(attendances),0) four_hour_pct,count(*) providers FROM mart.ae WHERE grain='provider' GROUP BY period,region,attendance_type;
