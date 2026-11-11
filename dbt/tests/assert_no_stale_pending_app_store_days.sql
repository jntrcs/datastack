-- 'pending' (no answer from Apple yet) is normal for the last few days: Apple
-- publishes late and the nightly job re-pulls the last 5 days. A pending day older
-- than that means the extractor stopped covering it -- the gap would otherwise hide
-- as NULLs forever. Returns the stuck days; passes when it returns 0 rows.

select date
from {{ ref('daily_kpis') }}
where app_store_report_status = 'pending'
  and date < current_date() - 6
