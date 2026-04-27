select
    'mko'       as supplier,
    teccode,
    code,
    name,
    tier,
    amount_under,
    price_per_unit,
    cliche_cost,
    min_job_cost

from {{ ref('stg_mko_print_prices') }}
