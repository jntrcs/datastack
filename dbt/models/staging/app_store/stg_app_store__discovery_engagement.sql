-- App Store impressions / page views / taps, typed, one restatement per event date.
-- Grain: one line of Apple's report (event x page x source x engagement x device x
-- OS x territory) for an event date, taken from the LATEST file that contains it.

with source as (

    select
        *,
        to_date(regexp_substr(_source_file, 'processing_date=([0-9-]+)', 1, 1, 'e'))
                                                    as processing_date
    from {{ source('app_store', 'analytics_discovery_engagement') }}

),

-- Same file loaded twice (re-pulled with new bytes) -> keep its latest load.
latest_load as (

    select * from source
    qualify _loaded_at = max(_loaded_at) over (partition by _source_file)

),

-- Apple re-sends each event date in later files. Those are restatements, not
-- increments, so keep only the newest file's rows for each date.
latest_restatement as (

    select * from latest_load
    qualify processing_date = max(processing_date) over (partition by date)

)

select
    {{ dbt_utils.generate_surrogate_key(['_source_file', '_source_row']) }}
                                                    as engagement_line_id,
    date::date                                      as event_date,
    processing_date,
    app_apple_identifier                            as app_id,
    event,
    page_type,
    source_type,
    engagement_type,
    device,
    platform_version,
    territory                                       as country_code,
    counts::int                                     as counts,
    unique_counts::int                              as unique_counts,
    _source_file,
    _loaded_at

from latest_restatement
