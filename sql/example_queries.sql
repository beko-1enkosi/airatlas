-- Recent observations with location and nullable weather context.
SELECT o.datetime_to_utc, o.location_id, l.location_name, o.parameter, o.unit,
       o.value, o.temperature_2m_c, o.relative_humidity_2m_pct,
       o.precipitation_mm, o.wind_speed_10m_kmh
FROM airatlas.observations AS o
JOIN airatlas.locations AS l ON l.location_id = o.location_id
ORDER BY o.datetime_to_utc DESC, o.location_id, o.sensor_id, o.parameter
LIMIT 100;

-- Average pollution by location. Never combine different source units.
SELECT location_id, parameter, unit, count(*) AS observations,
       avg(value) AS average_concentration
FROM airatlas.observations
GROUP BY location_id, parameter, unit
ORDER BY location_id, parameter, unit;

-- Pollution alongside available weather; descriptive comparison, not causation.
-- Each average uses only non-null values. Counts show different availability.
SELECT location_id, parameter, unit, count(*) AS observations,
       avg(value) AS average_concentration,
       count(temperature_2m_c) AS temperature_samples,
       count(relative_humidity_2m_pct) AS humidity_samples,
       count(wind_speed_10m_kmh) AS wind_samples,
       avg(temperature_2m_c) AS average_temperature_c,
       avg(relative_humidity_2m_pct) AS average_humidity_pct,
       avg(wind_speed_10m_kmh) AS average_wind_kmh
FROM airatlas.observations
GROUP BY location_id, parameter, unit
ORDER BY location_id, parameter, unit;

-- Daily trend uses the UTC date of measurement-period end.
-- These are observation-weighted averages, not duration-weighted estimates.
SELECT measurement_date_utc, location_id, parameter, unit,
       count(*) AS observations, avg(value) AS average_concentration
FROM airatlas.observations
GROUP BY measurement_date_utc, location_id, parameter, unit
ORDER BY measurement_date_utc, location_id, parameter, unit;
