with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/product/{{ var('run_date') }}/variants.parquet')
)

select
    product_ref,
    matnr,
    refct                   as sku_code,
    colour                  as colour_code,
    colourname              as colour_name,
    size,
    image500px              as image_url_500px

from source
