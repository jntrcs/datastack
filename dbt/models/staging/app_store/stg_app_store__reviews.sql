-- Written App Store reviews as of the most recent daily extract: one row per review.
-- Each daily file is the FULL list, so "current" = the latest file. A review that
-- the reviewer deleted is simply absent from it.
-- Grain: review_id.

with source as (

    select * from {{ source('app_store', 'reviews_daily') }}
    qualify _loaded_at = max(_loaded_at) over (partition by _source_file)

),

latest_snapshot as (

    select
        *,
        to_date(regexp_substr(_source_file, 'snapshot_date=([0-9-]+)', 1, 1, 'e'))
                                                        as snapshot_date
    from source
    qualify snapshot_date = max(snapshot_date) over ()

)

select
    review.value:id::string                             as review_id,
    latest_snapshot.record:app_id::string               as app_id,
    review.value:attributes:rating::int                 as rating,
    review.value:attributes:title::string               as title,
    review.value:attributes:body::string                as body,
    review.value:attributes:reviewerNickname::string    as reviewer_nickname,
    review.value:attributes:createdDate::timestamp_tz   as created_at,
    -- Apple's review territory is ISO alpha-3 (USA, CAN), unlike the alpha-2 codes
    -- in the ratings lookup (us, ca).
    review.value:attributes:territory::string           as territory_alpha3,
    latest_snapshot.snapshot_date,
    latest_snapshot.record:extracted_at::timestamp_tz   as extracted_at
from latest_snapshot,
    lateral flatten(input => latest_snapshot.record:reviews) as review
