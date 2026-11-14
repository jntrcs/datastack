-- Serving layer: what reads the marts and shows them to people.
--   SNOWFLAKE_REVERSE_ETL_PUBLIC_KEY=$(grep -v -- ----- ~/.snowflake/reverse_etl_svc_key.pub | tr -d '\n') \
--     uv run python -m warehouse.sf -f warehouse/sql/05_serving.sql

-- 1. Reverse ETL: GitHub Actions exports the dashboard marts to JSON for
--    jacksoncurtis.me. REPORTER only, so a leaked key can read marts and nothing else
--    (not RAW, not write anywhere). Same pattern as LOADER_SVC / TRANSFORMER_SVC.
USE ROLE SECURITYADMIN;

CREATE USER IF NOT EXISTS REVERSE_ETL_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = REPORTER
  DEFAULT_WAREHOUSE = REPORTING_WH
  COMMENT = 'GitHub Actions nightly export of dashboard marts to R2 for jacksoncurtis.me.';
ALTER USER REVERSE_ETL_SVC SET RSA_PUBLIC_KEY = '{{SNOWFLAKE_REVERSE_ETL_PUBLIC_KEY}}';
GRANT ROLE REPORTER TO USER REVERSE_ETL_SVC;

-- 2. Streamlit in Snowflake. The app is OWNED by REPORTER, and a SiS app runs with
--    its owner's rights: it can read exactly what REPORTER can (the marts), and
--    viewers need no grants on the tables themselves. The schema lives outside dbt's
--    STAGING/MARTS so a dbt rebuild never touches it.
USE ROLE SYSADMIN;
CREATE SCHEMA IF NOT EXISTS ANALYTICS.DASHBOARDS
  COMMENT = 'Streamlit apps and their source stages (owned by REPORTER).';
GRANT USAGE, CREATE STREAMLIT, CREATE STAGE ON SCHEMA ANALYTICS.DASHBOARDS TO ROLE REPORTER;
