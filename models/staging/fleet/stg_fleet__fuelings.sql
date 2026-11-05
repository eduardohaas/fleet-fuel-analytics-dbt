with source as (
    select * from {{ source('fleet_app', 'fleet_fuelings') }}
),

deduplicated as (
    -- Drivers sometimes tap "send" twice: same vehicle, time, liters and amount under a new id.
    select *
    from source
    qualify row_number() over (
        partition by plate, fueled_at, liters, total_paid
        order by fueling_id
    ) = 1
)

select
    d.fueling_id,
    d.plate,
    d.driver_id,
    d.fueled_at::timestamp                          as fueled_at,
    d.fueled_at::date                               as fueled_on,
    date_trunc('month', d.fueled_at::timestamp)::date as reference_month,
    upper(strip_accents(d.city))                    as municipality,
    d.station_name,
    map.anp_product,
    d.liters::decimal(10, 2)                        as liters,
    d.unit_price::decimal(8, 3)                     as unit_price_brl,
    d.total_paid::decimal(12, 2)                    as total_paid_brl,
    d.odometer_km
from deduplicated as d
left join {{ ref('app_product_mapping') }} as map
    on d.product = map.app_product
