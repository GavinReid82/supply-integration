-- Canonical production days lookup across all suppliers.
-- MKO does not provide production day data — XDC only for now.
-- To add a supplier: add a union all branch referencing its seed or int_* model.
{% if env_var('XDC_BASE_URL', '') != '' %}
select
    'xdc'                as supplier,
    print_technique,
    print_color_quantity,
    area_min,
    area_max,
    quantity_min,
    production_days
from {{ ref('xdc_production_days') }}
{% else %}
select
    cast(null as varchar) as supplier,
    cast(null as varchar) as print_technique,
    cast(null as integer) as print_color_quantity,
    cast(null as integer) as area_min,
    cast(null as integer) as area_max,
    cast(null as integer) as quantity_min,
    cast(null as integer) as production_days
where 1=0
{% endif %}
