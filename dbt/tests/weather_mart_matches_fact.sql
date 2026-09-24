-- Require exactly the groups and counts supplied by matched fact observations.
with expected as (
    select measurement_date_utc, location_id, parameter, unit,
        count(*) as observation_count
    from {{ ref('fct_air_quality_observations') }}
    where has_weather_context
    group by measurement_date_utc, location_id, parameter, unit
)
select coalesce(e.location_id, a.location_id) as location_id,
    coalesce(e.parameter, a.parameter) as parameter,
    coalesce(e.unit, a.unit) as unit
from expected as e
full join {{ ref('agg_pollution_weather') }} as a
    using (measurement_date_utc, location_id, parameter, unit)
where e.observation_count is distinct from a.observation_count
    or a.observation_count <= 0
    or a.temperature_observation_count not between 0 and a.observation_count
    or a.humidity_observation_count not between 0 and a.observation_count
    or a.precipitation_observation_count not between 0 and a.observation_count
    or a.wind_observation_count not between 0 and a.observation_count
