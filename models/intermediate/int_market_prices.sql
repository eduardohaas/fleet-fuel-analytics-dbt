-- Market benchmark per city, month and product from ANP's real station prices.
-- ANP skips some months (no April 2026 file) and some cities in some months, so the
-- benchmark falls back to the last month the city was observed, then to the state median.
with observed as (
    select municipality, reference_month, anp_product,
           median(sale_price_brl)              as median_price_brl,
           quantile_cont(sale_price_brl, 0.25) as p25_price_brl,
           quantile_cont(sale_price_brl, 0.75) as p75_price_brl,
           count(*)                            as observations
    from {{ ref('stg_anp__fuel_prices') }}
    group by all
),

state as (
    select reference_month, anp_product, median(sale_price_brl) as state_median_price_brl
    from {{ ref('stg_anp__fuel_prices') }}
    group by all
),

month_spine as (
    select unnest(generate_series(
        (select min(reference_month) from {{ ref('stg_fleet__fuelings') }}),
        (select max(reference_month) from {{ ref('stg_fleet__fuelings') }}),
        interval 1 month))::date as reference_month
),

grid as (
    select c.municipality, p.anp_product, m.reference_month
    from (select distinct municipality from {{ ref('stg_fleet__fuelings') }}) as c
    cross join (select distinct anp_product from {{ ref('fuel_compatibility') }}) as p
    cross join month_spine as m
),

filled as (
    select
        g.municipality,
        g.anp_product,
        g.reference_month,
        o.median_price_brl                                                   as observed_median_brl,
        last_value(o.median_price_brl ignore nulls) over (
            partition by g.municipality, g.anp_product order by g.reference_month
        )                                                                    as carried_median_brl,
        o.p25_price_brl,
        o.p75_price_brl,
        coalesce(o.observations, 0)                                          as observations,
        s.state_median_price_brl
    from grid as g
    left join observed as o using (municipality, anp_product, reference_month)
    left join state as s using (anp_product, reference_month)
)

select
    municipality,
    anp_product,
    reference_month,
    coalesce(observed_median_brl, carried_median_brl, state_median_price_brl) as benchmark_price_brl,
    case
        when observed_median_brl is not null then 'city_month'
        when carried_median_brl is not null then 'city_last_known_month'
        else 'state_month'
    end as benchmark_source,
    p25_price_brl,
    p75_price_brl,
    observations
from filled
