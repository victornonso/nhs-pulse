select * from {{ source('published','ae') }} where grain='provider'
