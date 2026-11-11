-- Service users for automation (GitHub Actions). Humans log in as themselves;
-- pipelines get their own TYPE = SERVICE users: key-pair only (no password, so
-- no MFA prompts), one role each, so a leaked CI key can only do that role's job.
--   SNOWFLAKE_LOADER_PUBLIC_KEY=$(...) uv run python -m warehouse.sf -f warehouse/sql/03_service_users.sql

USE ROLE SECURITYADMIN;

CREATE USER IF NOT EXISTS LOADER_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = LOADER
  DEFAULT_WAREHOUSE = LOADING_WH
  COMMENT = 'GitHub Actions nightly COPY INTO from R2.';
ALTER USER LOADER_SVC SET RSA_PUBLIC_KEY = '{{SNOWFLAKE_LOADER_PUBLIC_KEY}}';
GRANT ROLE LOADER TO USER LOADER_SVC;

-- dbt in CI: builds ANALYTICS.STAGING/MARTS from RAW. TRANSFORMER can read RAW and
-- write ANALYTICS, but can't load RAW or grant anything.
--   SNOWFLAKE_TRANSFORMER_PUBLIC_KEY=$(...) uv run python -m warehouse.sf -f warehouse/sql/03_service_users.sql
CREATE USER IF NOT EXISTS TRANSFORMER_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = TRANSFORMER
  DEFAULT_WAREHOUSE = TRANSFORMING_WH
  COMMENT = 'GitHub Actions nightly dbt build.';
ALTER USER TRANSFORMER_SVC SET RSA_PUBLIC_KEY = '{{SNOWFLAKE_TRANSFORMER_PUBLIC_KEY}}';
GRANT ROLE TRANSFORMER TO USER TRANSFORMER_SVC;
