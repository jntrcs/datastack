"""Extract App Store Connect Analytics Reports (impressions, page views, downloads,
sessions), untouched.

Usage:
    uv run python -m extract.asc_analytics                        # last 5 processing days
    uv run python -m extract.asc_analytics 2026-10-07             # one processing day
    uv run python -m extract.asc_analytics 2026-10-07 2026-11-11  # a range (backfill)
    uv run python -m extract.asc_analytics all                    # everything Apple still has

Each report instance lands at:
    raw/app_store/analytics/<report>/processing_date=YYYY-MM-DD/segment_<n>.tsv.gz

How Apple serves these (different from the Sales report):
- An "ONGOING" report request (already created for the app) makes Apple generate
  one *instance* per report per day. Each instance has 1+ *segments*: gzipped TSV
  files behind short-lived pre-signed URLs.
- Instances are keyed by PROCESSING date, not event date. One instance can hold rows
  for several earlier event dates (late-arriving data), so we partition raw files by
  processing date and let dbt regroup rows by the `Date` column.
- Apple keeps only ~35 days of daily instances. That's why this runs nightly: data
  we don't land before it ages out is gone for good.
"""

import os
import sys
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

from . import asc
from .landing import land

PREFIX = "raw/app_store/analytics"
LOOKBACK_DAYS = 5

# Our slug -> Apple report name. Names are stable across apps; the report IDs we
# look up at runtime from the app's ONGOING request.
REPORTS = {
    "discovery_engagement": "App Store Discovery and Engagement Standard",
    "downloads": "App Downloads Standard",
    "sessions": "App Sessions Standard",
}


def paged(tok: str, path: str, params: dict) -> list[dict]:
    """GET every page of a list endpoint (Apple paginates via links.next)."""
    out: list[dict] = []
    url: str | None = path
    while url:
        res = asc.get(tok, url, params)
        res.raise_for_status()
        body = res.json()
        out += body["data"]
        nxt = body.get("links", {}).get("next")
        url, params = (nxt.removeprefix(asc.API), {}) if nxt else (None, {})
    return out


def ongoing_request_id(tok: str, app_id: str) -> str:
    reqs = paged(tok, f"/v1/apps/{app_id}/analyticsReportRequests", {"filter[accessType]": "ONGOING"})
    live = [r for r in reqs if not r["attributes"].get("stoppedDueToInactivity")]
    if not live:
        raise SystemExit("No active ONGOING analytics report request for this app (needs an Admin key to create).")
    return live[0]["id"]


def report_ids(tok: str, request_id: str) -> dict[str, str]:
    by_name = {r["attributes"]["name"]: r["id"] for r in paged(tok, f"/v1/analyticsReportRequests/{request_id}/reports", {"limit": 200})}
    missing = [n for n in REPORTS.values() if n not in by_name]
    if missing:
        raise SystemExit(f"Reports not found on request {request_id}: {missing}")
    return {slug: by_name[name] for slug, name in REPORTS.items()}


def extract_report(tok: str, slug: str, report_id: str, start: date | None, end: date | None) -> None:
    instances = paged(tok, f"/v1/analyticsReports/{report_id}/instances", {"filter[granularity]": "DAILY", "limit": 200})
    for inst in sorted(instances, key=lambda i: i["attributes"]["processingDate"]):
        day = date.fromisoformat(inst["attributes"]["processingDate"])
        if (start and day < start) or (end and day > end):
            continue
        segments = paged(tok, f"/v1/analyticsReportInstances/{inst['id']}/segments", {})
        # Sort so segment numbering is stable across re-runs (re-runs overwrite, not duplicate).
        for n, seg in enumerate(sorted(segments, key=lambda s: s["id"])):
            res = requests.get(seg["attributes"]["url"], timeout=120)  # pre-signed; no auth header
            res.raise_for_status()
            key = f"{PREFIX}/{slug}/processing_date={day.isoformat()}/segment_{n}.tsv.gz"
            print(f"{slug:<22} {day} {len(res.content):>7} bytes -> {land(key, res.content)}")


def main(argv: list[str]) -> None:
    load_dotenv()
    if argv[:1] == ["all"]:
        start = end = None
    else:
        end = date.fromisoformat(argv[1]) if len(argv) > 1 else date.today()
        start = date.fromisoformat(argv[0]) if argv else end - timedelta(days=LOOKBACK_DAYS)
        if len(argv) == 1:
            end = start

    tok = asc.token()
    request_id = ongoing_request_id(tok, os.environ.get("ASC_APP_ID", "6760903362"))
    for slug, report_id in report_ids(tok, request_id).items():
        extract_report(tok, slug, report_id, start, end)


if __name__ == "__main__":
    main(sys.argv[1:])
