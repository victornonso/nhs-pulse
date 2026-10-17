select * from {{ ref('fct_bed_organisation_quarter') }} where extract(month from quarter) not in(1,4,7,10) or days_in_quarter not between 90 and 92
