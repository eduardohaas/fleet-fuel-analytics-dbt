-- Audit list: one row per fueling and broken rule, with a reason a fleet manager can read.
with flagged as (
    select * from {{ ref('fct_fuelings') }} where anomaly_count > 0
),

unpivoted as (
    select fueling_id, 'over_tank' as rule, format('{} L in a {} L tank', liters, v.tank_capacity_l) as reason
    from flagged join {{ ref('dim_vehicles') }} as v using (plate) where flag_over_tank
    union all
    select fueling_id, 'odometer_regression', format('odometer {} km is below a previous reading', odometer_km)
    from flagged where flag_odometer_regression
    union all
    select fueling_id, 'wrong_fuel', format('{} logged for a {}', anp_product, replace(vehicle_class, '_', ' '))
    from flagged where flag_wrong_fuel
    union all
    select fueling_id, 'price_above_market', format('paid {} vs {} city median ({}%)', unit_price_brl, round(benchmark_price_brl, 2), round(100 * price_premium_pct, 1))
    from flagged where flag_price_above_market
    union all
    select fueling_id, 'low_efficiency', format('{} km/l vs {} benchmark', round(km_per_liter, 2), benchmark_km_per_l)
    from flagged where flag_low_efficiency
)

select
    u.fueling_id,
    u.rule,
    u.reason,
    f.plate,
    f.driver_id,
    f.fueled_at,
    f.municipality,
    f.station_name,
    f.total_paid_brl
from unpivoted as u
inner join flagged as f using (fueling_id)
