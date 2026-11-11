-- Load raw files from R2 into RAW tables. Idempotent: safe to re-run nightly.
--   uv run python -m warehouse.sf -f warehouse/sql/02_raw_load.sql
--
-- How re-runs behave: COPY INTO remembers which files it has loaded (by name +
-- checksum, for 64 days) and skips them. The nightly extract re-pulls the last 5
-- days; a re-pulled file whose bytes changed gets loaded AGAIN as new rows. So RAW
-- can hold several versions of the same day -- dbt's staging models keep only
-- the latest version per file (_loaded_at). Append-only raw + dedupe downstream is
-- the standard ELT pattern.
--
-- Why not Snowpipe? It auto-loads on bucket event notifications, which R2 (as an
-- s3compat stage) doesn't support. A COPY after each nightly extract does the same job.

USE ROLE LOADER;
USE WAREHOUSE LOADING_WH;
USE SCHEMA RAW.LANDING;

-- {{...}} placeholders are filled from .env / CI secrets by warehouse/sf.py.
CREATE STAGE IF NOT EXISTS R2_RAW
  URL = 's3compat://datastack-raw/raw/'
  ENDPOINT = '{{R2_ACCOUNT_ID}}.r2.cloudflarestorage.com'
  CREDENTIALS = (AWS_KEY_ID = '{{R2_ACCESS_KEY_ID}}' AWS_SECRET_KEY = '{{R2_SECRET_ACCESS_KEY}}')
  COMMENT = 'The R2 landing bucket, raw/ prefix.';

CREATE FILE FORMAT IF NOT EXISTS TSV_GZ_HEADER
  TYPE = CSV FIELD_DELIMITER = '\t' SKIP_HEADER = 1 COMPRESSION = GZIP
  FIELD_OPTIONALLY_ENCLOSED_BY = NONE EMPTY_FIELD_AS_NULL = TRUE TRIM_SPACE = TRUE;

CREATE FILE FORMAT IF NOT EXISTS JSON_DOC TYPE = JSON;

-- ---------------------------------------------------------------- App Store sales
-- Every column as text, named like Apple's header. Typing happens in dbt.
CREATE TABLE IF NOT EXISTS RAW.APP_STORE.SALES_DAILY (
  provider VARCHAR, provider_country VARCHAR, sku VARCHAR, developer VARCHAR,
  title VARCHAR, version VARCHAR, product_type_identifier VARCHAR, units VARCHAR,
  developer_proceeds VARCHAR, begin_date VARCHAR, end_date VARCHAR,
  customer_currency VARCHAR, country_code VARCHAR, currency_of_proceeds VARCHAR,
  apple_identifier VARCHAR, customer_price VARCHAR, promo_code VARCHAR,
  parent_identifier VARCHAR, subscription VARCHAR, period VARCHAR, category VARCHAR,
  cmb VARCHAR, device VARCHAR, supported_platforms VARCHAR, proceeds_reason VARCHAR,
  preserved_pricing VARCHAR, client VARCHAR, order_type VARCHAR,
  contingent_app_name VARCHAR,
  _source_file VARCHAR, _source_file_modified TIMESTAMP_TZ, _source_row NUMBER,
  _loaded_at TIMESTAMP_TZ
);

COPY INTO RAW.APP_STORE.SALES_DAILY
FROM (
  SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
         $21,$22,$23,$24,$25,$26,$27,$28,$29,
         METADATA$FILENAME, METADATA$FILE_LAST_MODIFIED, METADATA$FILE_ROW_NUMBER,
         CURRENT_TIMESTAMP()
  FROM @R2_RAW/app_store/sales_daily/
)
PATTERN = '.*/sales[.]tsv[.]gz'
FILE_FORMAT = (FORMAT_NAME = TSV_GZ_HEADER);

-- File inventory: every object under app_store/sales_daily/, including the empty
-- _NO_REPORT markers the extractor writes for settled days Apple returned 404 for.
-- COPY can't load a zero-byte file as a row, so we record the stage LISTING instead.
-- This is how the warehouse tells "Apple confirmed no sales" (marker) apart from
-- "we have nothing for this day yet" (no object at all). Append-only, like COPY:
-- a new row only when a (path, md5) pair hasn't been seen before.
CREATE TABLE IF NOT EXISTS RAW.APP_STORE.SALES_DAILY_FILES (
  file_path VARCHAR, size_bytes NUMBER, md5 VARCHAR, last_modified VARCHAR,
  _listed_at TIMESTAMP_TZ
);

LIST @R2_RAW/app_store/sales_daily/;

INSERT INTO RAW.APP_STORE.SALES_DAILY_FILES
SELECT l."name", l."size", l."md5", l."last_modified", CURRENT_TIMESTAMP()
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) l
WHERE NOT EXISTS (
  SELECT 1 FROM RAW.APP_STORE.SALES_DAILY_FILES f
  WHERE f.file_path = l."name" AND f.md5 = l."md5"
);

-- ------------------------------------------------- App Store Analytics Reports
-- One file per (report, PROCESSING date). A file can hold rows for several earlier
-- event dates (`date` column), so dbt groups by `date`, not by file. Columns are
-- positional, in Apple's header order (checked identical across all files 2026-11-11).
CREATE TABLE IF NOT EXISTS RAW.APP_STORE.ANALYTICS_DISCOVERY_ENGAGEMENT (
  date VARCHAR, app_name VARCHAR, app_apple_identifier VARCHAR, event VARCHAR,
  page_type VARCHAR, source_type VARCHAR, engagement_type VARCHAR, device VARCHAR,
  platform_version VARCHAR, territory VARCHAR, counts VARCHAR, unique_counts VARCHAR,
  _source_file VARCHAR, _source_file_modified TIMESTAMP_TZ, _source_row NUMBER,
  _loaded_at TIMESTAMP_TZ
);

COPY INTO RAW.APP_STORE.ANALYTICS_DISCOVERY_ENGAGEMENT
FROM (
  SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
         METADATA$FILENAME, METADATA$FILE_LAST_MODIFIED, METADATA$FILE_ROW_NUMBER,
         CURRENT_TIMESTAMP()
  FROM @R2_RAW/app_store/analytics/discovery_engagement/
)
PATTERN = '.*/segment_[0-9]+[.]tsv[.]gz'
FILE_FORMAT = (FORMAT_NAME = TSV_GZ_HEADER);

CREATE TABLE IF NOT EXISTS RAW.APP_STORE.ANALYTICS_DOWNLOADS (
  date VARCHAR, app_name VARCHAR, app_apple_identifier VARCHAR, download_type VARCHAR,
  app_version VARCHAR, device VARCHAR, platform_version VARCHAR, source_type VARCHAR,
  page_type VARCHAR, pre_order VARCHAR, territory VARCHAR, counts VARCHAR,
  _source_file VARCHAR, _source_file_modified TIMESTAMP_TZ, _source_row NUMBER,
  _loaded_at TIMESTAMP_TZ
);

COPY INTO RAW.APP_STORE.ANALYTICS_DOWNLOADS
FROM (
  SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
         METADATA$FILENAME, METADATA$FILE_LAST_MODIFIED, METADATA$FILE_ROW_NUMBER,
         CURRENT_TIMESTAMP()
  FROM @R2_RAW/app_store/analytics/downloads/
)
PATTERN = '.*/segment_[0-9]+[.]tsv[.]gz'
FILE_FORMAT = (FORMAT_NAME = TSV_GZ_HEADER);

CREATE TABLE IF NOT EXISTS RAW.APP_STORE.ANALYTICS_SESSIONS (
  date VARCHAR, app_name VARCHAR, app_apple_identifier VARCHAR, app_version VARCHAR,
  device VARCHAR, platform_version VARCHAR, source_type VARCHAR, page_type VARCHAR,
  app_download_date VARCHAR, territory VARCHAR, sessions VARCHAR,
  total_session_duration VARCHAR, unique_devices VARCHAR,
  _source_file VARCHAR, _source_file_modified TIMESTAMP_TZ, _source_row NUMBER,
  _loaded_at TIMESTAMP_TZ
);

COPY INTO RAW.APP_STORE.ANALYTICS_SESSIONS
FROM (
  SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
         METADATA$FILENAME, METADATA$FILE_LAST_MODIFIED, METADATA$FILE_ROW_NUMBER,
         CURRENT_TIMESTAMP()
  FROM @R2_RAW/app_store/analytics/sessions/
)
PATTERN = '.*/segment_[0-9]+[.]tsv[.]gz'
FILE_FORMAT = (FORMAT_NAME = TSV_GZ_HEADER);

-- ------------------------------------------------------- Cloudflare Web Analytics
-- One row per file, the whole JSON document in a VARIANT column. dbt flattens it.
CREATE TABLE IF NOT EXISTS RAW.CLOUDFLARE.WEB_ANALYTICS_DAILY (
  record VARIANT,
  _source_file VARCHAR, _source_file_modified TIMESTAMP_TZ, _loaded_at TIMESTAMP_TZ
);

COPY INTO RAW.CLOUDFLARE.WEB_ANALYTICS_DAILY
FROM (
  SELECT $1, METADATA$FILENAME, METADATA$FILE_LAST_MODIFIED, CURRENT_TIMESTAMP()
  FROM @R2_RAW/cloudflare/web_analytics_daily/
)
PATTERN = '.*/pageloads[.]json'
FILE_FORMAT = (FORMAT_NAME = JSON_DOC);

-- ------------------------------------------------------------------ summary
SELECT 'app_store.sales_daily' AS tbl, COUNT(*) AS rows_, COUNT(DISTINCT _source_file) AS files,
       MIN(begin_date) AS first_, MAX(_loaded_at) AS last_loaded
FROM RAW.APP_STORE.SALES_DAILY
UNION ALL
SELECT 'cloudflare.web_analytics_daily', COUNT(*), COUNT(DISTINCT _source_file),
       MIN(record:variables:date::STRING), MAX(_loaded_at)
FROM RAW.CLOUDFLARE.WEB_ANALYTICS_DAILY
UNION ALL
SELECT 'app_store.analytics_discovery_engagement', COUNT(*), COUNT(DISTINCT _source_file), MIN(date), MAX(_loaded_at)
FROM RAW.APP_STORE.ANALYTICS_DISCOVERY_ENGAGEMENT
UNION ALL
SELECT 'app_store.analytics_downloads', COUNT(*), COUNT(DISTINCT _source_file), MIN(date), MAX(_loaded_at)
FROM RAW.APP_STORE.ANALYTICS_DOWNLOADS
UNION ALL
SELECT 'app_store.analytics_sessions', COUNT(*), COUNT(DISTINCT _source_file), MIN(date), MAX(_loaded_at)
FROM RAW.APP_STORE.ANALYTICS_SESSIONS;
