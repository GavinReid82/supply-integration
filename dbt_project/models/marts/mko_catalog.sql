with products as (
    select * from {{ ref('stg_mko_products') }}
),

-- Lowest price tier (tier 1 = smallest quantity = most common retail price)
min_prices as (
    select
        product_ref,
        min(unit_price) as min_unit_price,
        max(unit_price) as max_unit_price
    from {{ ref('stg_mko_prices') }}
    group by product_ref
),

-- Aggregate stock across all warehouses
stock_summary as (
    select
        product_ref,
        sum(stock_qty)                      as total_stock_qty,
        bool_or(in_stock_now)               as in_stock_now,
        min(available_date)                 as earliest_available_date
    from {{ ref('stg_mko_stock') }}
    group by product_ref
)

select
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
left join min_prices pr on p.product_ref = pr.product_ref
left join stock_summary s  on p.product_ref = s.product_ref
