-- Human (non-bot) website traffic per day, by page and where it came from.
-- Grain: visit_date x request_host x request_path x referer_host x country_code x device_type.

with pageloads as (

    select * from {{ ref('stg_cloudflare__pageloads') }}
    where not is_bot

)

select
    visit_date,
    request_host,
    request_path,
    coalesce(referer_host, '(direct)')  as referer_host,
    country_code,
    device_type,
    sum(pageviews)                      as pageviews,
    sum(visits)                         as visits,
    -- Flag estimated (sampled) numbers so nobody over-reads small counts.
    max(sample_interval) > 1            as is_sampled

from pageloads
group by all
