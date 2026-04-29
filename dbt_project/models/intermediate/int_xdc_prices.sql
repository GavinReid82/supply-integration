{{ config(tags=["xdc"]) }}
-- Variant-level price tiers joined to product. Uses the representative variant
-- (first by variant_id) per product so each product has one canonical price ladder.
with prices as (
    select * from {{ ref('stg_xdc_prices') }}
),

rep_variants as (
    select variant_id, product_id, product_name
    from {{ ref('stg_xdc_variants') }}
    qualify row_number() over (partition by product_id order by variant_id) = 1
)

select
    'xdc'           as supplier,
    v.product_id    as product_ref,
    v.product_name,
    p.tier,
    p.quantity_min  as min_qty,
    p.unit_price

from prices p
join rep_variants v on p.variant_id = v.variant_id
