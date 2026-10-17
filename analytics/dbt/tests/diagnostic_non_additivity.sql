select * from {{ ref('fct_diagnostic_provider_month') }} where commissioner_code<>'ALL' or upper(test)='TOTAL'
