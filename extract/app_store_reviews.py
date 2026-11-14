"""Extract every App Store customer review (written reviews, not star-only ratings).

Usage:
    uv run python -m extract.app_store_reviews

Lands one file per day, the full list as Apple returned it:
    raw/app_store/reviews_daily/snapshot_date=YYYY-MM-DD/reviews.json

Ratings vs reviews: a RATING is a star tap (app_store_ratings.py counts those from the
public lookup API). A REVIEW is a rating plus a title and text. Every review is also a
rating, so reviews <= ratings. Apple's public lookup only knows ratings; reviews come
from the App Store Connect API (/v1/apps/{id}/customerReviews), all storefronts at once.

Why a full daily snapshot rather than "new reviews since yesterday": the list is tiny,
and a reviewer can edit or delete a review. A full copy each day keeps deletions
visible (a review missing from today's file is gone) and needs no state.
"""

import json
from datetime import datetime, timezone

from dotenv import load_dotenv

from . import asc
from .landing import land

APP_ID = "6760903362"
PREFIX = "raw/app_store/reviews_daily"


def all_reviews(tok: str) -> list[dict]:
    out: list[dict] = []
    url: str | None = f"/v1/apps/{APP_ID}/customerReviews"
    params: dict = {"limit": 200, "sort": "-createdDate"}
    while url:
        res = asc.get(tok, url, params)
        res.raise_for_status()
        body = res.json()
        out += body["data"]
        nxt = body.get("links", {}).get("next")
        url, params = (nxt.removeprefix(asc.API), {}) if nxt else (None, {})
    return out


def main() -> None:
    load_dotenv()
    now = datetime.now(timezone.utc)
    reviews = all_reviews(asc.token())
    doc = {"app_id": APP_ID, "extracted_at": now.isoformat(), "reviews": reviews}
    key = f"{PREFIX}/snapshot_date={now.date().isoformat()}/reviews.json"
    print(f"{len(reviews)} reviews -> {land(key, json.dumps(doc).encode())}")


if __name__ == "__main__":
    main()
