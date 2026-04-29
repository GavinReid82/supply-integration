{{ config(tags=["xdc"]) }}
-- One row per product, derived from the variant feed (XDC has no separate product table).
-- Uses the lexically-first variant as the product representative.
with source as (
    select * from {{ ref('stg_xdc_variants') }}
),

ranked as (
    select *,
           row_number() over (partition by product_id order by variant_id) as rn
    from source
)

select
    'xdc'        as supplier,
    product_id   as product_ref,
    product_name,
    case
        when category ilike '%clothing%' then 'clothing'
        else 'corporate_gifts'
    end          as product_type,
    brand,
    category,
    subcategory,
    image_url,
    material     as composition,
    1            as min_order_qty,
    length_mm    as item_length_mm,
    width_mm     as item_width_mm,
    height_mm    as item_height_mm,
    weight_kg    as item_weight_kg

from ranked
where rn = 1
