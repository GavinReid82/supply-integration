-- Asserts (supplier, product_ref, teccode, areacode) is the unique key for print_options.
-- print_color is excluded from the key because at product level a given
-- technique+area always maps to a single colour count.
-- Returns rows on failure.
select
    supplier,
    product_ref,
    teccode,
    areacode,
    count(*) as cnt
from {{ ref('print_options') }}
group by supplier, product_ref, teccode, areacode
having count(*) > 1
