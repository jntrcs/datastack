-- The dashboard's weekly numbers. Built ONLY from daily_kpis, so the Streamlit app, the
-- website page and anyone querying Snowflake all get the same definitions.
-- Grain: week (Monday start). Complete calendar weeks only.
--
-- Partial periods lie: a week with 3 known days looks like a 57% drop. So each metric
-- is summed only when all 7 of its days are known, otherwise NULL. That covers both
-- "this week isn't over" and "tracking started mid-week" with one rule.

{% set additive = [
    'first_time_downloads',
    'app_store_impressions',
    'app_store_search_impressions',
    'app_store_product_page_views',
    'site_visits',
    'site_visits_jacksoncurtis_me',
    'site_visits_chronichealth',
] %}

with days as (

    select
        *,
        dateadd(day, 1 - dayofweekiso(date), date)  as week_start
    from {{ ref('daily_kpis') }}

),

weeks as (

    select
        week_start,
        dateadd(day, 6, week_start)                 as week_end,
        {% for col in additive %}
        iff(count({{ col }}) = 7, sum({{ col }}), null)  as {{ col }},
        {% endfor %}
        boolor_agg(is_site_sampled)                 as is_site_sampled
    from days
    group by week_start
    having count(*) = 7

)

select * from weeks
