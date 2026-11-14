"""Deploy dashboards/streamlit/ as a Streamlit in Snowflake app (idempotent).

    uv run python -m dashboards.deploy_streamlit

1. Upload the app's files to stage ANALYTICS.DASHBOARDS.STREAMLIT_SRC (PUT).
2. CREATE OR REPLACE STREAMLIT from that stage, owned by REPORTER, on the WAREHOUSE
   runtime: the app's Python runs on REPORTING_WH (XS), which stays on while someone
   has the app open and suspends afterwards. Snowflake's newer default is the
   container runtime (SYSTEM_COMPUTE_POOL_CPU), which is billed outside warehouses,
   so the DATASTACK_MONTHLY resource monitor wouldn't cap it. Warehouse runtime keeps
   the dashboard inside the 10-credit guardrail. Packages: environment.yml (Snowflake
   Anaconda channel; container runtime would use requirements.txt from PyPI instead).

Runs as you (the admin user) with role REPORTER, so REPORTER owns the app and the app
runs with REPORTER's rights. Needs warehouse/sql/05_serving.sql to have run once.
"""

from pathlib import Path

from dotenv import load_dotenv

from warehouse.sf import connect

SRC = Path(__file__).parent / "streamlit"
STAGE = "ANALYTICS.DASHBOARDS.STREAMLIT_SRC"
APP = "ANALYTICS.DASHBOARDS.CHRONIC_HEALTH_GROWTH"


def main() -> None:
    load_dotenv()
    with connect(role="REPORTER", warehouse="REPORTING_WH") as conn:
        cur = conn.cursor()
        cur.execute(f"CREATE STAGE IF NOT EXISTS {STAGE} DIRECTORY = (ENABLE = TRUE) "
                    "COMMENT = 'Source files for Streamlit apps (deployed by dashboards/deploy_streamlit.py)'")
        for f in ("streamlit_app.py", "environment.yml"):
            cur.execute(f"PUT 'file://{(SRC / f).resolve()}' @{STAGE}/chronic_health "
                        "AUTO_COMPRESS = FALSE OVERWRITE = TRUE")
            print(f"put {f}: {cur.fetchone()[6]}")
        cur.execute(f"""
            CREATE OR REPLACE STREAMLIT {APP}
              FROM '@{STAGE}/chronic_health'
              MAIN_FILE = 'streamlit_app.py'
              QUERY_WAREHOUSE = REPORTING_WH
              RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
              TITLE = 'Chronic Health growth'
              COMMENT = 'Downloads, ratings, reviews, funnel, site visits. Reads ANALYTICS.MARTS.'
        """)
        print(cur.fetchone()[0])
        org, acct = cur.execute("select current_organization_name(), current_account_name()").fetchone()
        print(f"open: https://app.snowflake.com/{org.lower()}/{acct.lower()}/#/streamlit-apps/{APP}")


if __name__ == "__main__":
    main()
