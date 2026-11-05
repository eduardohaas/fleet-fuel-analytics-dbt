-- Every fueling with consumption, market benchmark and anomaly flags.
-- Thresholds are dbt vars (dbt_project.yml), so the fleet manager can tune them without touching SQL.
with fuelings as (
    select f.*, v.vehicle_class, v.fuel_type, v.tank_capacity_l, v.benchmark_km_per_l
    from {{ ref('stg_fleet__fuelings') }} as f
    inner join {{ ref('stg_fleet__vehicles') }} as v using (plate)
),

with_distance as (
    select
        *,
        -- Compare with the highest odometer seen before, so one typo does not corrupt the next fueling.
        odometer_km - max(odometer_km) over (
            partition by plate order by fueled_at
            rows between unbounded preceding and 1 preceding
        ) as km_since_last
    from fuelings
),

enriched as (
    select
        d.*,
        case when d.km_since_last > 0 then d.km_since_last / d.liters end as km_per_liter,
        mp.benchmark_price_brl,
        mp.benchmark_source,
        c.anp_product is not null as is_compatible_product
    from with_distance as d
    left join {{ ref('int_market_prices') }} as mp
        on d.municipality = mp.municipality
       and d.reference_month = mp.reference_month
       and d.anp_product = mp.anp_product
    left join {{ ref('fuel_compatibility') }} as c
        on d.fuel_type = c.fuel_type
       and d.anp_product = c.anp_product
)

select
    fueling_id,
    plate,
    driver_id,
    fueled_at,
    fueled_on,
    reference_month,
    municipality,
    station_name,
    anp_product,
    vehicle_class,
    liters,
    unit_price_brl,
    total_paid_brl,
    odometer_km,
    km_since_last,
    km_per_liter,
    benchmark_km_per_l,
    benchmark_price_brl,
    benchmark_source,
    round(unit_price_brl / benchmark_price_brl - 1, 4)                              as price_premium_pct,
    round(greatest(unit_price_brl - benchmark_price_brl, 0) * liters, 2)            as overpaid_brl,
    liters > tank_capacity_l * {{ var('tank_tolerance') }}                          as flag_over_tank,
    coalesce(km_since_last <= 0, false)                                             as flag_odometer_regression,
    not is_compatible_product                                                       as flag_wrong_fuel,
    unit_price_brl > benchmark_price_brl * (1 + {{ var('price_premium_threshold') }}) as flag_price_above_market,
    coalesce(km_per_liter < benchmark_km_per_l * {{ var('efficiency_floor') }}, false) as flag_low_efficiency
from enriched
