-- Fleet-level monthly view: what fuel cost, what the market charged, what we overpaid.
with fleet as (
    select
        reference_month,
        count(*)                                                    as fuelings,
        sum(liters)                                                 as liters,
        sum(total_paid_brl)                                         as fuel_cost_brl,
        sum(overpaid_brl)                                           as overpaid_brl,
        sum(case when anomaly_count > 0 then 1 else 0 end)          as flagged_fuelings,
        round(sum(case when anp_product = 'DIESEL S10' then total_paid_brl end)
              / sum(case when anp_product = 'DIESEL S10' then liters end), 3) as diesel_paid_per_l_brl
    from {{ ref('fct_fuelings') }}
    group by all
),

km as (
    select reference_month, sum(km_driven) as km_driven
    from {{ ref('fct_vehicle_month') }}
    group by all
),

market as (
    select reference_month, median(sale_price_brl) as diesel_s10_rs_median_brl
    from {{ ref('stg_anp__fuel_prices') }}
    where anp_product = 'DIESEL S10'
    group by all
)

select
    fleet.*,
    km.km_driven,
    round(fleet.fuel_cost_brl / nullif(km.km_driven, 0), 3) as cost_per_km_brl,
    market.diesel_s10_rs_median_brl
from fleet
left join km using (reference_month)
left join market using (reference_month)
