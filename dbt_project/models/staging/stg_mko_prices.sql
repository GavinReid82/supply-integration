with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/price/{{ var('run_date') }}/price.parquet')
),

-- Unpivot 4 price tiers into one row per product/tier
unpivoted as (
    select ref as product_ref, name as product_name, 1 as tier,
           try_cast(section1 as integer) as min_qty, try_cast(price1 as decimal(10, 4)) as unit_price
    from source where section1 is not null

    union all
    select ref, name, 2, try_cast(section2 as integer), try_cast(price2 as decimal(10, 4))
    from source where section2 is not null

    union all
    select ref, name, 3, try_cast(section3 as integer), try_cast(price3 as decimal(10, 4))
    from source where section3 is not null

    union all
    select ref, name, 4, try_cast(section4 as integer), try_cast(price4 as decimal(10, 4))
    from source where section4 is not null
)

select * from unpivoted
