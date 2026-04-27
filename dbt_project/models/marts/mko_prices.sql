select * from {{ ref('prices') }} where supplier = 'mko'
