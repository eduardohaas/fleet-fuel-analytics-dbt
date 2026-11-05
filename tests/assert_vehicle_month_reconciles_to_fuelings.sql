-- The vehicle-month view must add up to exactly what was paid at the pump.
select
    (select sum(fuel_cost_brl) from {{ ref('fct_vehicle_month') }}) as vehicle_month_total,
    (select sum(total_paid_brl) from {{ ref('fct_fuelings') }})    as fuelings_total
where abs(vehicle_month_total - fuelings_total) > 0.01
