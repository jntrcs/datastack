-- One row per line of Apple's daily sales report, typed and deduplicated.
-- Grain: one report line (Apple doesn't give lines an ID, so we build one).

with source as (

    select * from {{ source('app_store', 'sales_daily') }}

),

-- If a file was loaded more than once (re-pulled with different bytes), keep only
-- the most recent load of it. Raw stays append-only; staging decides what's current.
latest_load as (

    select *
    from source
    qualify _loaded_at = max(_loaded_at) over (partition by _source_file)

),

renamed as (

    select
        {{ dbt_utils.generate_surrogate_key(['_source_file', '_source_row']) }}
                                                    as sales_line_id,
        to_date(begin_date, 'MM/DD/YYYY')           as report_date,
        apple_identifier                            as app_id,
        sku,
        title                                       as app_title,
        version                                     as app_version,
        product_type_identifier,
        units::int                                  as units,
        developer_proceeds::number(12, 2)           as developer_proceeds,
        customer_price::number(12, 2)               as customer_price,
        customer_currency,
        currency_of_proceeds,
        country_code,
        device,
        supported_platforms,
        category,
        promo_code,
        _source_file,
        _loaded_at

    from latest_load

)

select * from renamed
