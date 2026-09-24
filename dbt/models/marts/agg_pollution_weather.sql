-- Observation-weighted weather context, not causal or full-day weather estimates.
-- Do not sum precipitation: multiple observations can share the same weather hour.
select
    measurement_date_utc,
    location_id,
    parameter,
    unit,
    max(canonical_location_name) as location_name,
    count(*) as observation_count,
    avg(value) as average_pollution_value,
    avg(temperature_2m_c) as average_temperature_2m_c,
    avg(relative_humidity_2m_pct) as average_relative_humidity_2m_pct,
    avg(precipitation_mm) as average_precipitation_mm,
    avg(wind_speed_10m_kmh) as average_wind_speed_10m_kmh,
    count(temperature_2m_c) as temperature_observation_count,
    count(relative_humidity_2m_pct) as humidity_observation_count,
    count(precipitation_mm) as precipitation_observation_count,
    count(wind_speed_10m_kmh) as wind_observation_count
from {{ ref('fct_air_quality_observations') }}
where has_weather_context
group by measurement_date_utc, location_id, parameter, unit
