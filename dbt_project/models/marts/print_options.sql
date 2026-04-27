-- Canonical print options across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_print_options model.
select * from {{ ref('int_mko_print_options') }}
