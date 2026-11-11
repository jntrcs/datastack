-- App Store downloads from the Analytics Reports (not the Sales report), typed, one
-- restatement per event date. Has source/page attribution the Sales report lacks;
-- the Sales report (stg_app_store__sales) stays the source of truth for counts.
-- Grain: one report line for an event date, from the LATEST file containing it.

with source as (

    select
        *,
        to_date(regexp_substr(_source_file, 'processing_date=([0-9-]+)', 1, 1, 'e'))
                                                    as processing_date
    from {{ source('app_store', 'analytics_downloads') }}

),

latest_load as (

    select * from source
    qualify _loaded_at = max(_loaded_at) over (partition by _source_file)

),

latest_restatement as (

    select * from latest_load
    qualify processing_date = max(processing_date) over (partition by date)

)

select
    {{ dbt_utils.generate_surrogate_key(['_source_file', '_source_row']) }}
                                                    as download_line_id,
    date::date                                      as event_date,
    processing_date,
    app_apple_identifier                            as app_id,
    download_type,
    app_version,
    device,
    platform_version,
    source_type,
    page_type,
    pre_order is not null                           as is_pre_order,
    territory                                       as country_code,
    counts::int                                     as counts,
    _source_file,
    _loaded_at

from latest_restatement
