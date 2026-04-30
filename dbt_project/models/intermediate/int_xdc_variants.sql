{{ config(tags=["xdc"]) }}
-- Contract: (1) adds supplier='xdc', (2) renames to canonical column names,
-- (3) computes is_available via two-tier logic: non-Outlet lifecycle OR stock > subcategory threshold.
-- attribute_json is NULL — can be populated later from the 30+ variant attribute fields.
with variants as (
    select *
    from {{ ref('stg_xdc_variants') }}
    qualify row_number() over (partition by product_id, variant_id order by 1) = 1
),

stock as (
    select *
    from {{ ref('stg_xdc_stock') }}
    qualify row_number() over (partition by variant_id order by 1) = 1
),

thresholds as (
    select * from {{ ref('xdc_availability_thresholds') }}
),

availability as (
    select
        v.variant_id,
        coalesce(s.stock_qty, 0)                    as stock_qty,
        coalesce(t.threshold, 300)                  as threshold,
        -- Available if not Outlet lifecycle, OR if stock exceeds threshold (even for Outlet)
        (
            coalesce(v.productlifecycle, '') != 'Outlet'
            or coalesce(s.stock_qty, 0) > coalesce(t.threshold, 300)
        )                                           as is_available
    from variants v
    left join stock      s on v.variant_id = s.variant_id
    left join thresholds t on lower(v.subcategory) = lower(t.subcategory)
)

select
    'xdc'                                           as supplier,
    v.product_id                                    as product_ref,
    v.variant_id,
    null                                            as sku_code,
    v.hex_color                                     as colour_code,
    v.color                                         as colour_name,
    v.size,
    v.image_url,
    coalesce(a.is_available, false)                 as is_available,
    null                                            as attribute_json,
    null                                            as hs_code

from variants v
left join availability a on v.variant_id = a.variant_id
