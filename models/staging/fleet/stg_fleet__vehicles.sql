select
    v.plate,
    v.vehicle_model,
    m.vehicle_class,
    m.fuel_type,
    m.tank_capacity_l,
    m.benchmark_km_per_l,
    upper(strip_accents(v.home_base)) as home_base,
    v.model_year
from {{ source('fleet_app', 'fleet_vehicles') }} as v
left join {{ ref('vehicle_models') }} as m using (vehicle_model)
