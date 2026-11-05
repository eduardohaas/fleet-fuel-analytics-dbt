select
    driver_id,
    driver_name,
    upper(strip_accents(home_base)) as home_base
from {{ source('fleet_app', 'fleet_drivers') }}
