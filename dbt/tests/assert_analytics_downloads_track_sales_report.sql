-- Two Apple sources for the same thing should roughly agree. The Analytics Reports
-- and the Sales report count first-time downloads differently (day boundaries,
-- attribution), so daily numbers differ, but over 4 weeks they should be within 10%.
-- (2026-10-06 -> 11-09: 270 vs 278, 3%.) Warn, don't fail: the funnel isn't wrong if
-- this drifts, but a big gap means one source changed and someone should look.
{{ config(severity = 'warn') }}

with window_ as (

    select dateadd(day, -31, current_date()) as start_date,
           dateadd(day, -3, current_date())  as end_date   -- skip unsettled days

),

analytics as (

    select sum(first_time_downloads) as n
    from {{ ref('fct_app_store_funnel_daily') }}, window_
    where event_date between start_date and end_date

),

sales as (

    select sum(units) as n
    from {{ ref('fct_app_downloads_daily') }}, window_
    where event_type = 'first_download' and report_date between start_date and end_date

)

select analytics.n as analytics_downloads, sales.n as sales_downloads
from analytics, sales
where abs(analytics.n - sales.n) > 0.10 * sales.n
