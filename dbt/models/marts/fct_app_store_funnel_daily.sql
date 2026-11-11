-- The App Store funnel per day: impressions -> product page views -> Get taps ->
-- first-time downloads, by how people found the app (source), country and device.
-- Grain: event_date x app_id x source_type x country_code x device.
--
-- All four steps come from Apple's Analytics Reports so the ratios compare like with
-- like. For download COUNTS, the Sales report (fct_app_downloads_daily) is the source
-- of truth; the two agree within a few % per month but not day by day.
--
-- Coverage: Apple keeps ~35 days of files and each date first appears in the next
-- day's file, so dates before (oldest file - 1 day) are partial and excluded.

with engagement as (

    select
        event_date,
        app_id,
        source_type,
        country_code,
        device,
        sum(iff(event = 'Impression', counts, 0))                                 as impressions,
        sum(iff(event = 'Page view' and page_type = 'Product page', counts, 0))   as product_page_views,
        sum(iff(event = 'Tap' and engagement_type = 'Get', counts, 0))            as get_taps
    from {{ ref('stg_app_store__discovery_engagement') }}
    group by all

),

downloads as (

    select
        event_date,
        app_id,
        source_type,
        country_code,
        device,
        sum(iff(download_type = 'First-time download', counts, 0))  as first_time_downloads,
        sum(iff(download_type = 'Redownload', counts, 0))           as redownloads
    from {{ ref('stg_app_store__analytics_downloads') }}
    group by all

),

coverage as (

    select min(processing_date) - 1 as first_complete_date
    from {{ ref('stg_app_store__discovery_engagement') }}

),

joined as (

    -- Full outer join: a download can come from a source with no impressions that
    -- day (e.g. a direct link), and most impressions lead to no download.
    select
        coalesce(e.event_date, d.event_date)        as event_date,
        coalesce(e.app_id, d.app_id)                as app_id,
        coalesce(e.source_type, d.source_type)      as source_type,
        coalesce(e.country_code, d.country_code)    as country_code,
        coalesce(e.device, d.device)                as device,
        coalesce(e.impressions, 0)                  as impressions,
        coalesce(e.product_page_views, 0)           as product_page_views,
        coalesce(e.get_taps, 0)                     as get_taps,
        coalesce(d.first_time_downloads, 0)         as first_time_downloads,
        coalesce(d.redownloads, 0)                  as redownloads
    from engagement e
    full outer join downloads d
        on  d.event_date   = e.event_date
        and d.app_id       = e.app_id
        and d.source_type  = e.source_type
        and d.country_code = e.country_code
        and d.device       = e.device

)

select joined.*
from joined
cross join coverage
where joined.event_date >= coverage.first_complete_date
