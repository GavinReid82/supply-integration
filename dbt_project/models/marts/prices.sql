-- Canonical price tiers across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_prices model.
select * from {{ ref('int_mko_prices') }}
{% if env_var('XDC_BASE_URL', '') != '' %}
union all
select * from {{ ref('int_xdc_prices') }}
{% endif %}
