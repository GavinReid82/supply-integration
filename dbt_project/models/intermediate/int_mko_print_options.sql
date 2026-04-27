select
    'mko'       as supplier,
    product_ref,
    teccode,
    technique_name,
    areacode,
    area_name,
    max_colours,
    area_width_cm,
    area_height_cm,
    area_image_url,
    colour_layers,
    included_colours

from {{ ref('stg_mko_print_options') }}
