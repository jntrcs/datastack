-- Ratings as of the most recent extract: one row per storefront with >= 1 rating.
-- This is the "current state" view the snapshot (snapshots/) watches for changes.
-- Storefronts with 0 ratings are left out so they don't clutter the history; if a
-- storefront drops out, the snapshot closes its row (hard_deletes: invalidate).

select
    country_code,
    app_id,
    rating_count,
    average_rating,
    app_version,
    extracted_at
from {{ ref('stg_app_store__ratings') }}
where snapshot_date = (select max(snapshot_date) from {{ ref('stg_app_store__ratings') }})
  and rating_count > 0
