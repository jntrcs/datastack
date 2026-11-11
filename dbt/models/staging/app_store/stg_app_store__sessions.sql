-- In-app sessions from the Analytics Reports, typed, one restatement per event date.
-- Grain: one report line for an event date, from the LATEST file containing it.

with source as (

    select
        *,
        to_date(regexp_substr(_source_file, 'processing_date=([0-9-]+)', 1, 1, 'e'))
                                                    as processing_date
    from {{ source('app_store', 'analytics_sessions') }}

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
                                                    as session_line_id,
    date::date                                      as event_date,
    processing_date,
    app_apple_identifier                            as app_id,
    app_version,
    device,
    platform_version,
    source_type,
    page_type,
    app_download_date::date                         as app_download_date,
    territory                                       as country_code,
    sessions::int                                   as sessions,
    total_session_duration::int                     as total_session_seconds,
    unique_devices::int                             as unique_devices,
    _source_file,
    _loaded_at

from latest_restatement
