"""Extract Cloudflare Web Analytics (site visitors) for one day at a time.

Usage:
    uv run python -m extract.cf_web_analytics                         # yesterday
    uv run python -m extract.cf_web_analytics 2026-10-21 2026-11-09   # a range

Each day lands at:
    raw/cloudflare/web_analytics_daily/date=YYYY-MM-DD/pageloads.json

Unlike App Store sales, Cloudflare doesn't hand out raw event logs; the GraphQL
API returns pre-aggregated groups. So "raw" here means: the most granular grouping
the API allows (every dimension we might ever want), no filters (bots included,
every site on the account), saved exactly as returned along with the query that
produced it. Aggregating further, and dropping bots, happens in dbt.

Retention: Cloudflare keeps this dataset for 184 days (settings.notOlderThan =
15,897,600s). More importantly, it DOWNSAMPLES with age: as of 2026-11-10, days
older than ~8 days come back at sampleInterval=10 (1-in-10 sampling, counts are
x10 estimates), recent days at 1 (exact). Wide multi-day queries are also sampled
more heavily. So: run nightly, one day per query, to capture each day at full
fidelity. 2026-10-21..10-31 were already sampled when first extracted.

Field notes for modeling later:
  count            = page views in the group
  sum.visits       = page views that started a visit (came from another site / direct)
  avg.sampleInterval = 1 means unsampled; N means each row stands for ~N events
"""

import json
import os
import sys
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

from .landing import land

PREFIX = "raw/cloudflare/web_analytics_daily"
URL = "https://api.cloudflare.com/client/v4/graphql"

QUERY = """
query($acct: string!, $date: Date!) { viewer { accounts(filter: {accountTag: $acct}) {
  rumPageloadEventsAdaptiveGroups(limit: 10000, filter: {date: $date}) {
    count
    sum { visits }
    avg { sampleInterval }
    dimensions {
      date siteTag requestHost requestPath refererHost refererPath
      countryName deviceType userAgentBrowser userAgentOS bot navigationType
    }
  }
} } }
"""


def extract_day(day: date) -> str:
    variables = {"acct": os.environ["CF_ACCOUNT_ID"], "date": day.isoformat()}
    res = requests.post(
        URL,
        json={"query": QUERY, "variables": variables},
        headers={"Authorization": f"Bearer {os.environ['CF_API_TOKEN']}"},
        timeout=60,
    )
    res.raise_for_status()
    body = res.json()
    # GraphQL reports errors with HTTP 200, so check the body too.
    if body.get("errors"):
        raise RuntimeError(f"{day}: {body['errors']}")
    rows = body["data"]["viewer"]["accounts"][0]["rumPageloadEventsAdaptiveGroups"]
    if len(rows) >= 10000:
        raise RuntimeError(f"{day}: hit the 10,000-group limit; split the query")

    record = {
        "extracted_at": date.today().isoformat(),
        "query": QUERY,
        "variables": variables,
        "response": body,
    }
    key = f"{PREFIX}/date={day.isoformat()}/pageloads.json"
    return f"{len(rows):>4} groups -> " + land(key, json.dumps(record, indent=1).encode())


def main(argv: list[str]) -> None:
    load_dotenv()
    yesterday = date.today() - timedelta(days=1)
    start = date.fromisoformat(argv[0]) if argv else yesterday
    end = date.fromisoformat(argv[1]) if len(argv) > 1 else start
    day = start
    while day <= end:
        print(day, extract_day(day))
        day += timedelta(days=1)


if __name__ == "__main__":
    main(sys.argv[1:])
