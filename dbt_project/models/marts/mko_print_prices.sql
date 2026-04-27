select * from {{ ref('print_prices') }} where supplier = 'mko'
