{{ config(tags=["xdc"]) }}
-- Canonical 4D print price matrix: technique × color_count × area_range × quantity.
-- Unpivots 9 fixed quantity breakpoints; derives quantity_max via LEAD window function.
-- area_min/max converted from cm² to mm² (×100).
-- product_ref is NULL — XDC print prices are global (not per product), same as MKO.
with source as (
    select * from {{ ref('stg_xdc_print_prices') }}
),

unpivoted as (
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           1     as qty_break, price_quantity_1     as price_per_unit from source where price_quantity_1     is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           50,              price_quantity_50        from source where price_quantity_50        is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           100,             price_quantity_100       from source where price_quantity_100       is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           250,             price_quantity_250       from source where price_quantity_250       is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           500,             price_quantity_500       from source where price_quantity_500       is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           1000,            price_quantity_1000      from source where price_quantity_1000      is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           2500,            price_quantity_2500      from source where price_quantity_2500      is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           5000,            price_quantity_5000      from source where price_quantity_5000      is not null
    union all
    select print_technique, print_color_quantity, has_full_color, area_min_cm2, area_max_cm2, product_quantity_min, price_setup,
           10000,           price_quantity_10000     from source where price_quantity_10000     is not null
),

with_bounds as (
    select *,
        lead(qty_break) over (
            partition by print_technique, print_color_quantity, area_min_cm2
            order by qty_break
        ) - 1                                   as quantity_max_lead
    from unpivoted
)

select
    'xdc'                                       as supplier,
    null                                        as product_ref,
    print_technique                             as technique_code,
    print_technique                             as technique_name,
    null                                        as position_code,
    case
        when has_full_color                     then -1
        when print_color_quantity > 0           then print_color_quantity
        else null
    end                                         as color_count,
    try_cast(area_min_cm2 * 100 as integer)     as area_min_mm2,
    try_cast(area_max_cm2 * 100 as integer)     as area_max_mm2,
    greatest(
        coalesce(product_quantity_min, 1),
        qty_break
    )                                           as quantity_min,
    coalesce(quantity_max_lead, 9999999)        as quantity_max,
    price_per_unit,
    price_setup                                 as setup_cost,
    null                                        as min_job_cost

from with_bounds
where price_per_unit is not null
  and price_per_unit > 0
