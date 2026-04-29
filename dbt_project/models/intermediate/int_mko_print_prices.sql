with source as (
    select * from {{ ref('stg_mko_print_prices') }}
),

with_bounds as (
    select
        *,
        coalesce(
            lag(amount_under) over (partition by teccode, code order by tier),
            1
        ) as quantity_min
    from source
)

select
    'mko'            as supplier,
    null             as product_ref,
    teccode          as technique_code,
    name             as technique_name,
    code             as position_code,
    null             as color_count,
    null             as area_min_mm2,
    null             as area_max_mm2,
    quantity_min,
    amount_under - 1 as quantity_max,
    price_per_unit,
    cliche_cost      as setup_cost,
    min_job_cost

from with_bounds
