{{ config(tags=["xdc"]) }}
-- Distinct print technique / position combinations per product and variant.
-- maxprintwidthmm / maxprintheightmm are in mm in the raw feed; divided by 10 → cm
-- to match the canonical area_width_cm / area_height_cm schema.
with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/xdc/raw/print_option/{{ var('run_date') }}/print_option.parquet')
)

select distinct
    modelcode                                              as product_id,
    itemcode                                               as variant_id,
    printtechnique                                         as print_technique,
    printpositioncode                                      as print_position,
    try_cast(maxprintwidthmm  as decimal(8, 2)) / 10       as width_max_cm,
    try_cast(maxprintheightmm as decimal(8, 2)) / 10       as height_max_cm,
    try_cast(maxcolors        as integer)                  as print_color_quantity_max

from source
where modelcode      is not null
  and printtechnique is not null
  and printpositioncode is not null
