select * from {{ source('published','trend_seasonality') }}
