-- Headline numbers for the dashboards, as of the latest data. Grain: one row.

with daily as (

    select * from {{ ref('daily_kpis') }}

),

downloads as (

    select
        sum(first_time_downloads)                                   as total_first_time_downloads,
        max(iff(first_time_downloads is not null, date, null))      as downloads_as_of
    from daily

),

ratings as (

    -- Ratings are per storefront; the worldwide count is the sum, and the worldwide
    -- average is weighted by each storefront's count (not an average of averages).
    select
        sum(rating_count)                                           as ratings_count,
        div0(sum(rating_count * average_rating), sum(rating_count))::number(4, 2)
                                                                    as average_rating,
        max(extracted_at)::date                                     as ratings_as_of
    from {{ ref('stg_app_store__ratings_current') }}

),

reviews as (

    select
        count(*)                                                    as reviews_count,
        max(snapshot_date)                                          as reviews_as_of
    from {{ ref('stg_app_store__reviews') }}

)

select
    downloads.*,
    ratings.*,
    reviews.*,
    current_timestamp()                                             as built_at
from downloads
cross join ratings
cross join reviews
