-- After dedup, no vehicle can have two fuelings at the same minute with the same liters.
select plate, fueled_at, liters, count(*) as n
from {{ ref('fct_fuelings') }}
group by all
having count(*) > 1
