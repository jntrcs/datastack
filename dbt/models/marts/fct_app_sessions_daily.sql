-- In-app usage per day: how often people open Chronic Health and for how long.
-- Grain: event_date x app_id x app_version x device x country_code.
-- unique_devices is NOT summed here: one device on two app versions would count
-- twice. It's left out; use sessions and duration, which are additive.

with sessions as (

    select * from {{ ref('stg_app_store__sessions') }}

),

coverage as (

    select min(processing_date) - 1 as first_complete_date from sessions

)

select
    sessions.event_date,
    sessions.app_id,
    sessions.app_version,
    sessions.device,
    sessions.country_code,
    sum(sessions.sessions)                  as sessions,
    sum(sessions.total_session_seconds)     as total_session_seconds
from sessions
cross join coverage
where sessions.event_date >= coverage.first_complete_date
group by all
