{{ config(tags=["xdc"]) }}
-- Variant-level stock at the Romania (RO) facility.
with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/xdc/raw/stock/{{ var('run_date') }}/stock.parquet')
)

select
    itemcode                             as variant_id,
    try_cast(currentstock as integer)    as stock_qty

from source
where itemcode is not null
