-- Cloudflare Web Analytics page-load groups, flattened out of the raw JSON.
-- Grain: one group = one combination of (day, page, referrer, country, device,
-- browser, OS, bot flag, navigation type) as returned by Cloudflare.

with source as (

    select * from {{ source('cloudflare', 'web_analytics_daily') }}

),

latest_load as (

    select *
    from source
    qualify _loaded_at = max(_loaded_at) over (partition by _source_file)

),

-- Each file holds an array of groups; LATERAL FLATTEN turns it into one row each.
groups as (

    select
        latest_load._source_file,
        latest_load._loaded_at,
        g.index  as group_index,
        g.value  as grp
    from latest_load,
        lateral flatten(
            input => latest_load.record:response:data:viewer:accounts[0]:rumPageloadEventsAdaptiveGroups
        ) as g

),

renamed as (

    select
        {{ dbt_utils.generate_surrogate_key(['_source_file', 'group_index']) }}
                                                        as pageload_group_id,
        grp:dimensions:date::date                       as visit_date,
        grp:dimensions:siteTag::string                  as site_tag,
        grp:dimensions:requestHost::string              as request_host,
        grp:dimensions:requestPath::string              as request_path,
        nullif(grp:dimensions:refererHost::string, '')  as referer_host,
        nullif(grp:dimensions:refererPath::string, '')  as referer_path,
        grp:dimensions:countryName::string              as country_code,
        grp:dimensions:deviceType::string               as device_type,
        grp:dimensions:userAgentBrowser::string         as browser,
        grp:dimensions:userAgentOS::string              as operating_system,
        grp:dimensions:bot::int = 1                     as is_bot,
        grp:dimensions:navigationType::string           as navigation_type,
        -- Cloudflare already scales these up for sampling (sample_interval = 10
        -- means each sampled event stands for ~10), so they are estimates then.
        grp:count::int                                  as pageviews,
        grp:sum:visits::int                             as visits,
        grp:avg:sampleInterval::float                   as sample_interval,
        _source_file,
        _loaded_at

    from groups

)

select * from renamed
