{{ config(tags=["xdc"]) }}
-- Variant-level price tiers. XDC provides up to 6 quantity breaks per variant.
-- Unpivots wide format (qty1..6, itempricenet_qty1..6) into one row per variant/tier.
with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/xdc/raw/product_price/{{ var('run_date') }}/product_price.parquet')
),

unpivoted as (
    select itemcode as variant_id, 1 as tier,
           try_cast(qty1               as integer)        as quantity_min,
           try_cast(itempricenet_qty1  as decimal(10, 4)) as unit_price
    from source where qty1 is not null

    union all
    select itemcode, 2,
           try_cast(qty2 as integer), try_cast(itempricenet_qty2 as decimal(10, 4))
    from source where qty2 is not null

    union all
    select itemcode, 3,
           try_cast(qty3 as integer), try_cast(itempricenet_qty3 as decimal(10, 4))
    from source where qty3 is not null

    union all
    select itemcode, 4,
           try_cast(qty4 as integer), try_cast(itempricenet_qty4 as decimal(10, 4))
    from source where qty4 is not null

    union all
    select itemcode, 5,
           try_cast(qty5 as integer), try_cast(itempricenet_qty5 as decimal(10, 4))
    from source where qty5 is not null

    union all
    select itemcode, 6,
           try_cast(qty6 as integer), try_cast(itempricenet_qty6 as decimal(10, 4))
    from source where qty6 is not null
)

select * from unpivoted
where unit_price    is not null
  and quantity_min  is not null
