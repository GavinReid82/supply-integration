{{ config(tags=["xdc"]) }}
-- Variant-level stock rolled up to product level for the catalog stock summary.
with stock as (
    select * from {{ ref('stg_xdc_stock') }}
),

variants as (
    select distinct variant_id, product_id
    from {{ ref('stg_xdc_variants') }}
)

select
    'xdc'                        as supplier,
    v.product_id                 as product_ref,
    'RO'                         as warehouse,
    coalesce(s.stock_qty, 0)     as stock_qty,
    null                         as available_date

from stock s
join variants v on s.variant_id = v.variant_id
