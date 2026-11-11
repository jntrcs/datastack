"""Extract today's App Store rating count + average for every storefront.

Usage:
    uv run python -m extract.app_store_ratings

Lands one file per day:
    raw/app_store/ratings_daily/snapshot_date=YYYY-MM-DD/ratings.json

Apple's public lookup API (itunes.apple.com/lookup) only returns the CURRENT
value; there's no "ratings as of a date". So this can't be backfilled: each day's
file is the only record of that day. History is built downstream (RAW keeps every
daily file; the dbt snapshot records each change as a dated row).

Ratings are per storefront (country), so a worldwide total sums all of them. The
lookup refuses requests from Cloudflare IPs; GitHub Actions and laptops are fine.
"""

import json
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from .landing import land

APP_ID = "6760903362"
PREFIX = "raw/app_store/ratings_daily"

# App Store storefronts (same list as PersonalSite's worker/countries.js).
COUNTRIES = """
ae ag ai al am ao ar at au az ba bb bd be bf bg bh bj bm bn bo br bs bt bw by bz ca
cd cg ch ci cl cm cn co cr cv cy cz de dk dm do dz ec ee eg es fi fj fm fr ga gb gd
ge gh gm gr gt gw gy hk hn hr hu id ie il in iq is it jm jo jp ke kg kh kn kr kw ky
kz la lb lc lk lr lt lu lv ly ma md me mg mk ml mm mn mo mr ms mt mu mv mw mx my mz
na ne ng ni nl no np nr nz om pa pe pg ph pk pl pt pw py qa ro rs ru rw sa sb sc se
sg si sk sl sn sr st sv sz tc td th tj tm tn to tr tt tw tz ua ug us uy uz vc ve vg
vn vu xk ye za zm zw
""".split()


def lookup(country: str, attempts: int = 4) -> dict:
    """Apple's raw lookup response for one storefront (results=[] if not sold there)."""
    for attempt in range(attempts):
        try:
            res = requests.get(
                "https://itunes.apple.com/lookup", params={"id": APP_ID, "country": country}, timeout=30
            )
            if res.status_code == 200:
                return res.json()
        except requests.RequestException:
            pass
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"lookup {country} failed after {attempts} attempts")


def main() -> None:
    load_dotenv()
    now = datetime.now(timezone.utc)
    storefronts, failed = [], []
    for country in COUNTRIES:
        try:
            storefronts.append({"country": country, "response": lookup(country)})
        except RuntimeError as err:
            print(err)
            failed.append(country)

    # A partial file would look like ratings vanished in the failed countries.
    # Better to land nothing and let tomorrow's run catch the day.
    if failed:
        raise SystemExit(f"{len(failed)} lookups failed ({' '.join(failed)}); not landing a partial snapshot")

    doc = {"app_id": APP_ID, "extracted_at": now.isoformat(), "storefronts": storefronts}
    key = f"{PREFIX}/snapshot_date={now.date().isoformat()}/ratings.json"
    rated = [s for s in storefronts if s["response"].get("results") and s["response"]["results"][0].get("userRatingCount")]
    total = sum(s["response"]["results"][0]["userRatingCount"] for s in rated)
    print(f"{len(storefronts)} storefronts, {len(rated)} with ratings, {total} ratings -> {land(key, json.dumps(doc).encode())}")


if __name__ == "__main__":
    main()
