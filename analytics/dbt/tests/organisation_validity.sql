select * from {{ ref('dim_organisation_scd') }} where valid_to<=valid_from
