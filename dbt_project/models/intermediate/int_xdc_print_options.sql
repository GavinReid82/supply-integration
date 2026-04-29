{{ config(tags=["xdc"]) }}
-- One row per product × technique × position.
-- Deduplicates across variants; takes max colour count per combination.
-- Per-colour pricing applies only to specific techniques — others are forced to 0.
with source as (
    select * from {{ ref('stg_xdc_print_options') }}
),

per_colour_techniques as (
    -- Only these techniques price by colour count
    select technique from (values
        ('Embroidery'), ('Embroidery 3D'), ('Embroidery badge'),
        ('Pad Print'), ('Pad Print Drinkware'), ('Pad Print Low'),
        ('Screen Transfer OS'), ('SilkScreen'), ('SilkScreen Round')
    ) t(technique)
)

select
    'xdc'                                            as supplier,
    product_id                                       as product_ref,
    print_technique                                  as teccode,
    print_technique                                  as technique_name,
    print_position                                   as areacode,
    print_position                                   as area_name,
    case
        when pct.technique is not null
        then max(print_color_quantity_max)
        else 0
    end                                              as print_color,
    max(width_max_cm)                                as area_width_cm,
    max(height_max_cm)                               as area_height_cm,
    null                                             as area_image_url,
    null                                             as colour_layers,
    null                                             as included_colours

from source
left join per_colour_techniques pct on source.print_technique = pct.technique
group by product_id, print_technique, print_position, pct.technique
