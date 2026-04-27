select
    'mko'       as supplier,
    product_ref,
    product_name,
    tier,
    min_qty,
    unit_price

from {{ ref('stg_mko_prices') }}
