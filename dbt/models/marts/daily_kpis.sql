-- One row per day since app launch: the app funnel next to website traffic.
-- Grain: date. Every day is present (date spine), so charts and averages don't
-- silently skip quiet days. A quiet day is 0; an UNKNOWN day is NULL:
--   downloads: NULL until Apple has answered for that day (report or confirmed none)
--   site:      NULL before Cloudflare tracking started

{% set app_id = '6760903362' %}
{% set launch_date = '2026-04-02' %}

with days as (

    {{ dbt_utils.date_spine(
        datepart='day',
        start_date="'" ~ launch_date ~ "'::date",
        end_date='current_date()'
    ) }}

),

downloads as (

    select
        report_date,
        sum(iff(event_type = 'first_download', units, 0))  as first_time_downloads,
        sum(iff(event_type = 'redownload', units, 0))      as redownloads,
        sum(iff(event_type = 'update', units, 0))          as updates
    from {{ ref('fct_app_downloads_daily') }}
    where app_id = '{{ app_id }}'
    group by 1

),

app_store_days as (

    -- Days Apple has answered for. Absent = not published yet / not extracted.
    select report_date, report_status from {{ ref('stg_app_store__report_days') }}

),

site as (

    select
        visit_date,
        sum(pageviews)                                                     as site_pageviews,
        sum(visits)                                                        as site_visits,
        sum(iff(request_path like '/projects/chronic-health%', pageviews, 0))
                                                                           as chronic_health_page_views,
        boolor_agg(is_sampled)                                             as is_site_sampled
    from {{ ref('fct_site_traffic_daily') }}
    group by 1

),

site_coverage as (

    -- Cloudflare tracking started later than the app launched. Before this date,
    -- site numbers are unknown (NULL), not zero.
    select min(visit_date) as first_site_date from {{ ref('stg_cloudflare__pageloads') }}

)

select
    days.date_day                                       as date,
    iff(app_store_days.report_date is not null, coalesce(downloads.first_time_downloads, 0), null)
                                                        as first_time_downloads,
    iff(app_store_days.report_date is not null, coalesce(downloads.redownloads, 0), null)
                                                        as redownloads,
    iff(app_store_days.report_date is not null, coalesce(downloads.updates, 0), null)
                                                        as updates,
    coalesce(app_store_days.report_status, 'pending')   as app_store_report_status,
    iff(days.date_day >= site_coverage.first_site_date, coalesce(site.site_pageviews, 0), null)
                                                        as site_pageviews,
    iff(days.date_day >= site_coverage.first_site_date, coalesce(site.site_visits, 0), null)
                                                        as site_visits,
    iff(days.date_day >= site_coverage.first_site_date, coalesce(site.chronic_health_page_views, 0), null)
                                                        as chronic_health_page_views,
    coalesce(site.is_site_sampled, false)               as is_site_sampled

from days
cross join site_coverage
left join app_store_days on app_store_days.report_date = days.date_day
left join downloads on downloads.report_date = days.date_day
left join site on site.visit_date = days.date_day
