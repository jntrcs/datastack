-- Reconciliation test: the warehouse must agree with the number the live site
-- showed (590 first-time downloads through 2026-11-08, checked 2026-11-10 against
-- jacksoncurtis.me/api/app-stats). A singular test passes when it returns 0 rows.
-- If Apple ever restates history, this fails loudly instead of numbers drifting.

select sum(first_time_downloads) as total
from {{ ref('daily_kpis') }}
where date <= '2026-11-08'
having sum(first_time_downloads) != 590
