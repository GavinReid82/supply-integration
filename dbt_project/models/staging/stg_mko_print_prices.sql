with source as (
    select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/print/*/print_price.parquet')
),

-- Unpivot up to 7 quantity tiers into one row per technique/tier.
-- amount_under is the upper bound: price applies when quantity < amount_under.
-- Tiers with amount_under = 0 are unused placeholders and are excluded.
unpivoted as (
    select teccode, code, name,
           try_cast(cliche  as decimal(10, 2)) as cliche_cost,
           try_cast(minjob  as decimal(10, 2)) as min_job_cost,
           1 as tier,
           try_cast(amountunder1 as integer)   as amount_under,
           try_cast(price1       as decimal(10, 4)) as price_per_unit
    from source
    where try_cast(amountunder1 as integer) > 0

    union all
    select teccode, code, name,
           try_cast(cliche as decimal(10, 2)), try_cast(minjob as decimal(10, 2)),
           2, try_cast(amountunder2 as integer), try_cast(price2 as decimal(10, 4))
    from source where try_cast(amountunder2 as integer) > 0

    union all
    select teccode, code, name,
           try_cast(cliche as decimal(10, 2)), try_cast(minjob as decimal(10, 2)),
           3, try_cast(amountunder3 as integer), try_cast(price3 as decimal(10, 4))
    from source where try_cast(amountunder3 as integer) > 0

    union all
    select teccode, code, name,
           try_cast(cliche as decimal(10, 2)), try_cast(minjob as decimal(10, 2)),
           4, try_cast(amountunder4 as integer), try_cast(price4 as decimal(10, 4))
    from source where try_cast(amountunder4 as integer) > 0

    union all
    select teccode, code, name,
           try_cast(cliche as decimal(10, 2)), try_cast(minjob as decimal(10, 2)),
           5, try_cast(amountunder5 as integer), try_cast(price5 as decimal(10, 4))
    from source where try_cast(amountunder5 as integer) > 0

    union all
    select teccode, code, name,
           try_cast(cliche as decimal(10, 2)), try_cast(minjob as decimal(10, 2)),
           6, try_cast(amountunder6 as integer), try_cast(price6 as decimal(10, 4))
    from source where try_cast(amountunder6 as integer) > 0

    union all
    select teccode, code, name,
           try_cast(cliche as decimal(10, 2)), try_cast(minjob as decimal(10, 2)),
           7, try_cast(amountunder7 as integer), try_cast(price7 as decimal(10, 4))
    from source where try_cast(amountunder7 as integer) > 0
)

select * from unpivoted
