-- App Store ratings per storefront per day, flattened from the daily lookup files.
-- Grain: snapshot_date x country_code. Only storefronts where the app is sold.

with source as (

    select * from {{ source('app_store', 'ratings_daily') }}
    -- Same file loaded twice (re-pulled same day) -> keep its latest load.
    qualify _loaded_at = max(_loaded_at) over (partition by _source_file)

),

storefronts as (

    select
        to_date(regexp_substr(source._source_file, 'snapshot_date=([0-9-]+)', 1, 1, 'e'))
                                                        as snapshot_date,
        source.record:extracted_at::timestamp_tz        as extracted_at,
        storefront.value:country::string                as country_code,
        storefront.value:response:results[0]            as app
    from source,
        lateral flatten(input => source.record:storefronts) as storefront

)

select
    snapshot_date,
    country_code,
    app:trackId::string                                 as app_id,
    coalesce(app:userRatingCount::int, 0)               as rating_count,
    -- Apple says 0.0 when there are no ratings; that's "unknown", not zero stars.
    iff(app:userRatingCount::int > 0, app:averageUserRating::number(4, 3), null)
                                                        as average_rating,
    coalesce(app:userRatingCountForCurrentVersion::int, 0)
                                                        as rating_count_current_version,
    app:version::string                                 as app_version,
    extracted_at
from storefronts
where app is not null   -- results: [] means the app isn't sold in that storefront
