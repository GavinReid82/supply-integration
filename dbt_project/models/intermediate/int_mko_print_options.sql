with source as (
    select * from {{ ref('stg_mko_print_options') }}
),

-- Collapse duplicates that arise when multiple S3 date-partitions are read.
-- Some rows share the same (product_ref, teccode, areacode) but have different
-- area dimensions because the supplier updated them between extractions.
-- MAX picks the most permissive value; technique_name is stable per teccode.
deduped as (
    select
        product_ref,
        teccode,
        max(technique_name)                as technique_name,
        areacode,
        max(area_name)                     as area_name,
        max(max_colours)                   as max_colours,
        max(area_width_cm)                 as area_width_cm,
        max(area_height_cm)                as area_height_cm,
        max(area_image_url)                as area_image_url,
        max(colour_layers)                 as colour_layers,
        max(included_colours)              as included_colours
    from source
    group by product_ref, teccode, areacode
)

select
    'mko'                                                                    as supplier,
    product_ref,
    teccode,
    trim(regexp_replace(technique_name, '\s*\(FULLCOLOR\)', '', 'g'))        as technique_name,
    areacode,
    area_name,
    case
        when technique_name ilike '%FULLCOLOR%' then -1::bigint
        else cast(max_colours as bigint)
    end                                                                      as print_color,
    area_width_cm,
    area_height_cm,
    area_image_url,
    colour_layers,
    included_colours

from deduped
