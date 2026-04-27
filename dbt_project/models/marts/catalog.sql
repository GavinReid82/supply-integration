-- Canonical product catalog: one row per supplier/product.
-- To add a supplier: add union all branches to each CTE below.
-- NOTE: never put ref() calls inside SQL comments — dbt resolves them even there.
with products as (
    select * from {{ ref('int_mko_products') }}
),

min_prices as (
    select
        supplier,
        product_ref,
        min(unit_price) as min_unit_price,
        max(unit_price) as max_unit_price
    from {{ ref('int_mko_prices') }}
    group by supplier, product_ref
),

stock_summary as (
    select
        supplier,
        product_ref,
        sum(stock_qty)              as total_stock_qty,
        bool_or(in_stock_now)       as in_stock_now,
        min(available_date)         as earliest_available_date
    from {{ ref('int_mko_stock') }}
    group by supplier, product_ref
)

select
    p.supplier,
    p.product_ref,
    p.product_name,
    p.product_type,
    p.brand,
    p.category_name_1,
    p.category_name_2,
    p.min_order_qty,
    p.item_length_mm,
    p.item_width_mm,
    p.item_height_mm,
    p.item_weight_kg,
    p.composition,
    p.imagemain,

    pr.min_unit_price,
    pr.max_unit_price,

    s.total_stock_qty,
    s.in_stock_now,
    s.earliest_available_date

from products p
left join min_prices   pr on p.supplier = pr.supplier and p.product_ref = pr.product_ref
left join stock_summary s  on p.supplier = s.supplier  and p.product_ref = s.product_ref
