{{ config(materialized='incremental', incremental_strategy='append') }}

-- ANP publishes text: 'DD/MM/YYYY' dates and decimal commas. Incremental by source file:
-- a new monthly file is processed once, old files are never re-read.
select
    upper(strip_accents(municipality))                          as municipality,
    station_cnpj,
    product                                                     as anp_product,
    strptime(collected_on, '%d/%m/%Y')::date                    as collected_on,
    make_date(source_year, source_month, 1)                     as reference_month,
    replace(sale_price, ',', '.')::decimal(8, 3)                as sale_price_brl,
    brand,
    source_file
from {{ source('anp', 'anp_fuel_prices') }}
where sale_price is not null
{% if is_incremental() %}
  and source_file not in (select distinct source_file from {{ this }})
{% endif %}
