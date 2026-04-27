select
    'mko'       as supplier,
    product_ref,
    matnr,
    sku_code,
    colour_code,
    colour_name,
    size,
    image_url_500px

from {{ ref('stg_mko_variants') }}
