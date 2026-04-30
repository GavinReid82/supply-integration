with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/print/{{ var('run_date') }}/print.parquet')
)

select
    product_ref,
    teccode,
    tecname                              as technique_name,
    try_cast(colour_layers as integer)   as colour_layers,
    try_cast(includedcolour as integer)  as included_colours,
    areacode,
    areaname                             as area_name,
    try_cast(maxcolour as integer)       as max_colours,
    try_cast(areawidth as decimal(8, 2)) as area_width_cm,
    try_cast(areahight as decimal(8, 2)) as area_height_cm,
    areaimg                              as area_image_url

from source
where teccode is not null
  and areacode is not null
