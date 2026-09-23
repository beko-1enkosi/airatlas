select
    location_id,
    location_name,
    latitude,
    longitude,
    weather_latitude,
    weather_longitude
from {{ source('airatlas_warehouse', 'locations') }}
