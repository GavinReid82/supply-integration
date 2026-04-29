-- Asserts (supplier, product_ref) is unique in the catalog mart.
-- Returns rows on failure.
select
    supplier,
    product_ref,
    count(*) as cnt
from {{ ref('catalog') }}
group by supplier, product_ref
having count(*) > 1
