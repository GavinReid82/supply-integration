with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/product/*/products.parquet')
)

select
    ref                                         as product_ref,
    name                                        as product_name,
    type                                        as product_type,
    brand,
    printcode,
    keywords,
    composition,

    -- dimensions (cast from varchar)
    try_cast(item_long      as decimal(10, 2))  as item_length_mm,
    try_cast(item_width     as decimal(10, 2))  as item_width_mm,
    try_cast(item_hight     as decimal(10, 2))  as item_height_mm,
    try_cast(item_weight    as decimal(10, 4))  as item_weight_kg,

    -- minimum order
    try_cast(order_min_product as integer)      as min_order_qty,

    -- categories (up to 3 levels — extend if needed)
    category_ref_1,
    category_name_1,
    category_ref_2,
    category_name_2,
    category_ref_3,
    category_name_3,

    imagemain,

    -- links
    link360,
    linkvideo

from source
qualify row_number() over (partition by ref order by ref) = 1
