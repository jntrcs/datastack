"""Reverse ETL: export the dashboard marts to one JSON file for jacksoncurtis.me.

    uv run python -m serve.site_export                 # Snowflake -> R2
    uv run python -m serve.site_export --out x.json    # ...and also write a local copy

"Reverse" because data usually flows INTO the warehouse; this pushes modeled results
OUT of it, to where an operational tool (here, a website) can use them. The site never
talks to Snowflake: it reads this small file from R2 through its own Worker. That keeps
Snowflake credentials out of the website, keeps page loads from waking a warehouse
(cost!), and means the site still works if Snowflake is down (it shows last night's file).

Runs as REVERSE_ETL_SVC (REPORTER role: read marts, nothing else) after the nightly
dbt build. Lands at r2://datastack-raw/serve/site/dashboard.json, a different prefix
from raw/ (the Snowflake stage only ever reads raw/).
"""

import datetime as dt
import decimal
import json
import os
import sys

from dotenv import load_dotenv

from extract.landing import _r2_client
from warehouse.sf import connect

KEY = "serve/site/dashboard.json"
SCHEMA = os.environ.get("SITE_EXPORT_SCHEMA", "ANALYTICS.MARTS")

WEEKLY_COLUMNS = [
    "week_start",
    "first_time_downloads",
    "app_store_search_impressions",
    "app_store_product_page_views",
    "site_visits_jacksoncurtis_me",
    "site_visits_chronichealth",
    "is_site_sampled",
]


def _plain(v):
    if isinstance(v, decimal.Decimal):
        return float(v) if v % 1 else int(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def query(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    return [{c: _plain(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def build() -> dict:
    with connect(prefix="REVERSE_ETL_", role="REPORTER", warehouse="REPORTING_WH") as conn:
        cur = conn.cursor()
        current = query(cur, f"select * from {SCHEMA}.current_kpis")
        weekly = query(cur, f"select {', '.join(WEEKLY_COLUMNS)} from {SCHEMA}.weekly_kpis order by week_start")
    if len(current) != 1:
        raise SystemExit(f"expected 1 row in current_kpis, got {len(current)}")
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": f"{SCHEMA}.current_kpis + weekly_kpis (dbt), exported by serve/site_export.py",
        "current": current[0],
        "weekly": weekly,
    }


def main(argv: list[str]) -> None:
    load_dotenv()
    doc = build()
    body = json.dumps(doc, indent=1).encode()
    if "--out" in argv:
        path = argv[argv.index("--out") + 1]
        with open(path, "wb") as f:
            f.write(body)
        print(f"wrote {path}")
    bucket = os.environ.get("LANDING", "r2://datastack-raw").removeprefix("r2://")
    _r2_client().put_object(Bucket=bucket, Key=KEY, Body=body, ContentType="application/json")
    c = doc["current"]
    print(f"{len(doc['weekly'])} weeks, {c['total_first_time_downloads']} downloads -> r2://{bucket}/{KEY}")


if __name__ == "__main__":
    main(sys.argv[1:])
