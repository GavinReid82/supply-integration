with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/stock/{{ var('run_date') }}/stock.parquet')
)

select
    ref                                                 as product_ref,
    warehouse,
    try_cast(stock as integer)                          as stock_qty,
    case
        when lower(available) = 'immediately' then current_date
        else try_cast(available as date)
    end                                                 as available_date,
    available = 'immediately'                           as in_stock_now

from source
