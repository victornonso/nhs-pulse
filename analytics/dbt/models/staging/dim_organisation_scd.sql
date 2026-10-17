select code,name,org_type,valid_from,coalesce(valid_to,lead(valid_from) over(partition by code order by valid_from)) valid_to,status,ods from {{ source('reference','organisation') }}
