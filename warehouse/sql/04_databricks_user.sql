-- Service user for Databricks Lakehouse Federation: Databricks registers Snowflake's
-- ANALYTICS database as a foreign catalog and queries the dbt marts in place (no copy).
-- REPORTER only: it can read what dbt grants to REPORTER (the marts) and nothing else.
--   SNOWFLAKE_DATABRICKS_PUBLIC_KEY=$(grep -v -- ----- ~/.snowflake/databricks_svc_key.pub | tr -d '\n') \
--     uv run python -m warehouse.sf -f warehouse/sql/04_databricks_user.sql

USE ROLE SECURITYADMIN;

CREATE USER IF NOT EXISTS DATABRICKS_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = REPORTER
  DEFAULT_WAREHOUSE = REPORTING_WH
  COMMENT = 'Databricks Lakehouse Federation (read-only marts for ML/forecasting).';
ALTER USER DATABRICKS_SVC SET RSA_PUBLIC_KEY = '{{SNOWFLAKE_DATABRICKS_PUBLIC_KEY}}';
GRANT ROLE REPORTER TO USER DATABRICKS_SVC;

-- dbt grants SELECT on each mart table to REPORTER, but table grants are useless
-- without USAGE on the schema. Found 2026-11-12: DATABRICKS_SVC was the first login
-- ever to use REPORTER, so the gap had never shown. Schemas outlive dbt rebuilds,
-- so a one-time grant sticks. (SECURITYADMIN has MANAGE GRANTS.)
GRANT USAGE ON SCHEMA ANALYTICS.MARTS TO ROLE REPORTER;
