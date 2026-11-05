-- Fuel cost and consumption per vehicle and month.
select
    f.plate,
    f.reference_month,
    v.vehicle_model,
    v.vehicle_class,
    v.home_base,
    count(*)                                                        as fuelings,
    sum(f.liters)                                                   as liters,
    sum(f.total_paid_brl)                                           as fuel_cost_brl,
    sum(case when not f.flag_odometer_regression then f.km_since_last end) as km_driven,
    round(sum(case when not f.flag_odometer_regression then f.km_since_last end)
          / nullif(sum(case when f.km_since_last > 0 then f.liters end), 0), 2) as km_per_liter,
    any_value(v.benchmark_km_per_l)                                 as benchmark_km_per_l,
    round(sum(f.total_paid_brl)
          / nullif(sum(case when not f.flag_odometer_regression then f.km_since_last end), 0), 3) as cost_per_km_brl,
    sum(f.overpaid_brl)                                             as overpaid_brl,
    sum(case when f.anomaly_count > 0 then 1 else 0 end)            as flagged_fuelings
from {{ ref('fct_fuelings') }} as f
inner join {{ ref('dim_vehicles') }} as v using (plate)
group by all
