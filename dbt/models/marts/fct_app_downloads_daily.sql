-- App Store transactions per day, by country, device and event type.
-- Grain: report_date x app_id x country_code x device x event_type.

with sales as (

    select * from {{ ref('stg_app_store__sales') }}

),

product_types as (

    select * from {{ ref('app_store_product_types') }}

)

select
    sales.report_date,
    sales.app_id,
    sales.country_code,
    sales.device,
    coalesce(product_types.event_type, 'unknown')  as event_type,
    sum(sales.units)                               as units

from sales
left join product_types
    on sales.product_type_identifier = product_types.product_type_identifier

group by all
