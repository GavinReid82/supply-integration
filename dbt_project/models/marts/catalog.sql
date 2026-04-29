-- Canonical product catalog: one row per supplier/product.
-- To add a supplier: add conditional union all branches to each CTE below.
-- XDC is activated when XDC_PRODUCT_URL env var is set.
-- NOTE: never put ref() calls inside SQL comments — dbt resolves them even there.
with products as (
    select supplier, product_ref, product_name, product_type, brand, category, subcategory,
           min_order_qty, item_length_mm, item_width_mm, item_height_mm, item_weight_kg,
           composition, image_url
    from {{ ref('int_mko_products') }}
    {% if env_var('XDC_BASE_URL', '') != '' %}
    union all
    select supplier, product_ref, product_name, product_type, brand, category, subcategory,
           min_order_qty, item_length_mm, item_width_mm, item_height_mm, item_weight_kg,
           composition, image_url
    from {{ ref('int_xdc_products') }}
    {% endif %}
),

all_prices as (
    select supplier, product_ref, unit_price from {{ ref('int_mko_prices') }}
    {% if env_var('XDC_BASE_URL', '') != '' %}
    union all
    select supplier, product_ref, unit_price from {{ ref('int_xdc_prices') }}
    {% endif %}
),

min_prices as (
    select
        supplier,
        product_ref,
        min(unit_price) as min_unit_price,
        max(unit_price) as max_unit_price
    from all_prices
    group by supplier, product_ref
),

all_stock as (
    select supplier, product_ref, stock_qty, available_date from {{ ref('int_mko_stock') }}
    {% if env_var('XDC_BASE_URL', '') != '' %}
    union all
    select supplier, product_ref, stock_qty, available_date from {{ ref('int_xdc_stock') }}
    {% endif %}
),

stock_summary as (
    select
        supplier,
        product_ref,
        sum(stock_qty)          as total_stock_qty,
        min(available_date)     as earliest_available_date
    from all_stock
    group by supplier, product_ref
),

availability as (
    select supplier, product_ref, bool_or(is_available) as in_stock_now
    from {{ ref('variants') }}
    group by supplier, product_ref
)

select
    p.supplier,
    p.product_ref,
    p.product_name,
    p.product_type,
    p.brand,
    p.category,
    p.subcategory,
    p.min_order_qty,
    p.item_length_mm,
    p.item_width_mm,
    p.item_height_mm,
    p.item_weight_kg,
    p.composition,
    p.image_url,

    pr.min_unit_price,
    pr.max_unit_price,

    s.total_stock_qty,
    a.in_stock_now,
    s.earliest_available_date

from products p
left join min_prices    pr on p.supplier = pr.supplier and p.product_ref = pr.product_ref
left join stock_summary s  on p.supplier = s.supplier  and p.product_ref = s.product_ref
left join availability  a  on p.supplier = a.supplier  and p.product_ref = a.product_ref
