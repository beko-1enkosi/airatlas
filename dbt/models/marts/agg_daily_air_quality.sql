-- Names are descriptive; stable IDs, pollutant and unit define the grain.
-- Averages are observation-weighted, not time-weighted.
select
    measurement_date_utc,
    location_id,
    parameter,
    unit,
    max(canonical_location_name) as location_name,
    count(*) as observation_count,
    avg(value) as average_value,
    min(value) as minimum_value,
    max(value) as maximum_value,
    count(*) filter (where has_weather_context) as weather_context_count,
    100.0 * count(*) filter (where has_weather_context) / count(*) as weather_context_percentage
from {{ ref('fct_air_quality_observations') }}
group by measurement_date_utc, location_id, parameter, unit
