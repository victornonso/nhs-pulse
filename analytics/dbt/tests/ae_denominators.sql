select * from {{ ref('fct_ae_provider_month') }} where over_four>attendances or attendances<0
