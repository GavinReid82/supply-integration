{{ config(tags=["xdc"]) }}
-- Global print price matrix: technique × color_count × area_range.
-- 9 fixed quantity breakpoints stored as named columns; unpivoted in the intermediate layer.
-- area_min / area_max are already in cm² in the raw feed; converted to mm² (×100) in int_xdc_print_prices.
with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/xdc/raw/print_option_price/*/print_option_price.parquet')
)

select
    printtechnique                                          as print_technique,
    try_cast(nrofcolors         as integer)                 as print_color_quantity,
    try_cast(fullcolor          as boolean)                 as has_full_color,
    try_cast(printareafromcm2   as decimal(10, 4))          as area_min_cm2,
    try_cast(printareatocm2     as decimal(10, 4))          as area_max_cm2,
    try_cast(moqprintorder      as integer)                 as product_quantity_min,
    try_cast(setupnet           as decimal(10, 2))          as price_setup,
    try_cast(printpricenet_1    as decimal(10, 4))          as price_quantity_1,
    try_cast(printpricenet_50   as decimal(10, 4))          as price_quantity_50,
    try_cast(printpricenet_100  as decimal(10, 4))          as price_quantity_100,
    try_cast(printpricenet_250  as decimal(10, 4))          as price_quantity_250,
    try_cast(printpricenet_500  as decimal(10, 4))          as price_quantity_500,
    try_cast(printpricenet_1000 as decimal(10, 4))          as price_quantity_1000,
    try_cast(printpricenet_2500 as decimal(10, 4))          as price_quantity_2500,
    try_cast(printpricenet_5000 as decimal(10, 4))          as price_quantity_5000,
    try_cast(printpricenet_10000 as decimal(10, 4))         as price_quantity_10000

from source
where printtechnique is not null
