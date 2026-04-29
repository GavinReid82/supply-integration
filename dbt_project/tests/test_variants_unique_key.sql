-- Asserts variant_id is unique across all suppliers in the variants mart.
-- Returns rows on failure.
select
    variant_id,
    count(*) as cnt
from {{ ref('variants') }}
group by variant_id
having count(*) > 1
