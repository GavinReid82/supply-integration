-- Canonical print technique prices across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_print_prices model.
select * from {{ ref('int_mko_print_prices') }}
