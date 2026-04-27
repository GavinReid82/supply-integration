-- Canonical variants across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_variants model.
select * from {{ ref('int_mko_variants') }}
