{{ config(tags=["xdc"]) }}
-- One row per variant. Product and variant data are in a single XDC feed.
-- Renamed from the actual Excel/parquet column names to logical names used downstream.
-- Dimensions: raw feed is cm → converted to mm. Weight: raw feed is grams → converted to kg.
with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/xdc/raw/product/*/product.parquet')
)

select
    modelcode                                            as product_id,
    itemcode                                             as variant_id,
    itemname                                             as product_name,
    longdescription                                      as description,
    brand,
    maincategory                                         as category,
    subcategory,
    material,
    color,
    hexcolor1                                            as hex_color,
    textilesize                                          as size,
    try_cast(itemlengthcm    as decimal(8, 2)) * 10      as length_mm,
    try_cast(itemwidthcm     as decimal(8, 2)) * 10      as width_mm,
    try_cast(itemheightcm    as decimal(8, 2)) * 10      as height_mm,
    try_cast(itemdiametercm  as decimal(8, 2)) * 10      as diameter_mm,
    try_cast(itemweightnetgr as decimal(10, 3)) / 1000   as weight_kg,
    commoditycode                                        as hscode,
    try_cast(outercartonqty  as integer)                 as quantity_per_box,
    mainimage                                            as image_url,
    productlifecycle

from source
where modelcode is not null
  and itemcode  is not null
