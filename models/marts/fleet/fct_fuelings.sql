{{ config(
    materialized='incremental',
    unique_key='fueling_id',
    incremental_strategy='delete+insert'
) }}

-- One row per fueling. Incremental with a 7-day lookback: drivers submit late and fix typos.
select
    *,
    (flag_over_tank::int + flag_odometer_regression::int + flag_wrong_fuel::int
     + flag_price_above_market::int + flag_low_efficiency::int) as anomaly_count
from {{ ref('int_fuelings_flagged') }}
{% if is_incremental() %}
where fueled_at >= (select max(fueled_at) - interval 7 day from {{ this }})
{% endif %}
