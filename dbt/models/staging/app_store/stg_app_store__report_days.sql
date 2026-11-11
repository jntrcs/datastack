-- One row per day the extractor has an answer from Apple for.
-- Grain: report_date.
--
-- A day ABSENT from this model means we don't know yet (Apple hasn't published, or
-- the extract missed it). That's different from 'no_sales', which means Apple
-- answered 404 for a settled day (the extractor's _NO_REPORT marker). Marts use
-- this to show unknown days as NULL instead of a misleading 0.

with files as (

    select * from {{ source('app_store', 'sales_daily_files') }}

),

parsed as (

    select
        to_date(regexp_substr(file_path, 'report_date=(\\d{4}-\\d{2}-\\d{2})', 1, 1, 'e', 1))
                                                    as report_date,
        file_path like '%/sales.tsv.gz'             as is_report,
        file_path like '%/_NO_REPORT'               as is_no_report_marker,
        _listed_at
    from files

)

select
    report_date,
    -- A real report wins over a marker (Apple could publish late, after the marker).
    iff(boolor_agg(is_report), 'published', 'no_sales')  as report_status,
    min(_listed_at)                                      as first_seen_at
from parsed
where is_report or is_no_report_marker
group by 1
