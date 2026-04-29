select
    'mko'       as supplier,
    product_ref,
    teccode,
    -- Strip " (FULLCOLOR)" suffix; names like "FULLCOLOR AND DOMING PRINTING" are left intact
    TRIM(REGEXP_REPLACE(technique_name, '\s*\(FULLCOLOR\)', '', 'g')) as technique_name,
    areacode,
    area_name,
    -- -1 = full color (any name containing FULLCOLOR), otherwise the spot-colour count
    CASE
        WHEN technique_name ILIKE '%FULLCOLOR%' THEN -1::BIGINT
        ELSE CAST(max_colours AS BIGINT)
    END                                                                 as print_color,
    area_width_cm,
    area_height_cm,
    area_image_url,
    colour_layers,
    included_colours

from {{ ref('stg_mko_print_options') }}
