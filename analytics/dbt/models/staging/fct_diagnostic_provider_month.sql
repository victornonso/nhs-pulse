select * from {{ ref('stg_diagnostics_monthly') }} where grain='provider'
