-- Asserts (supplier, product_ref, variant_id) is unique in the variants mart.
-- The same matnr (variant_id) can appear under multiple MKO products; product_ref
-- is part of the grain.
select
    supplier,
    product_ref,
    variant_id,
    count(*) as cnt
from {{ ref('variants') }}
group by supplier, product_ref, variant_id
having count(*) > 1
