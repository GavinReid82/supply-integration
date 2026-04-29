with variants as (
    select * from {{ ref('stg_mko_variants') }}
),

availability as (
    select product_ref, bool_or(in_stock_now) as is_available
    from {{ ref('stg_mko_stock') }}
    group by product_ref
)

select
    'mko'                           as supplier,
    v.product_ref,
    v.matnr                         as variant_id,
    v.sku_code,
    v.colour_code,
    v.colour_name,
    v.size,
    v.image_url_500px               as image_url,
    coalesce(a.is_available, false) as is_available,
    null                            as attribute_json

from variants v
left join availability a on v.product_ref = a.product_ref
qualify row_number() over (partition by v.product_ref, v.matnr order by 1) = 1
