"""Extract App Store Connect daily SALES/SUMMARY reports, untouched.

Usage:
    uv run python -m extract.asc_sales                      # yesterday
    uv run python -m extract.asc_sales 2026-04-02           # one day
    uv run python -m extract.asc_sales 2026-04-02 2026-11-09  # a range (backfill)

Each day lands at:
    raw/app_store/sales_daily/report_date=YYYY-MM-DD/sales.tsv.gz

We keep Apple's gzipped TSV exactly as returned — every app, every product type,
updates and redownloads included. Deciding what counts as a "download" is a
business rule, so it belongs in dbt, not here (ELT).

Apple returns 404 both for days with no sales rows AND for days it hasn't
published yet. For days older than SETTLED_AFTER_DAYS we land an empty marker file
so the raw zone records "we asked, Apple had nothing" as distinct from "we never
asked". For recent days we land nothing; the nightly job re-pulls the last few
days, so a late report lands on a later run.
"""

import sys
from datetime import date, timedelta

from dotenv import load_dotenv

from . import asc
from .landing import land

PREFIX = "raw/app_store/sales_daily"
SETTLED_AFTER_DAYS = 4


def extract_day(tok: str, day: date, vendor: str) -> str:
    res = asc.get(
        tok,
        "/v1/salesReports",
        {
            "filter[frequency]": "DAILY",
            "filter[reportType]": "SALES",
            "filter[reportSubType]": "SUMMARY",
            "filter[version]": "1_1",
            "filter[vendorNumber]": vendor,
            "filter[reportDate]": day.isoformat(),
        },
        accept="application/a-gzip",
    )
    part = f"{PREFIX}/report_date={day.isoformat()}"
    if res.status_code == 404:
        if (date.today() - day).days < SETTLED_AFTER_DAYS:
            return "not published yet, will retry on a later run"
        return "no report  -> " + land(f"{part}/_NO_REPORT", b"")
    res.raise_for_status()
    return f"{len(res.content):>6} bytes -> " + land(f"{part}/sales.tsv.gz", res.content)


def main(argv: list[str]) -> None:
    import os

    load_dotenv()
    yesterday = date.today() - timedelta(days=1)
    start = date.fromisoformat(argv[0]) if argv else yesterday
    end = date.fromisoformat(argv[1]) if len(argv) > 1 else start

    tok = asc.token()
    vendor = os.environ["ASC_VENDOR_NUMBER"]
    day = start
    while day <= end:
        print(day, extract_day(tok, day, vendor))
        day += timedelta(days=1)


if __name__ == "__main__":
    main(sys.argv[1:])
