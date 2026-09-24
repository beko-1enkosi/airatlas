with summaries as (
    select 'daily' as mart, location_id, parameter, unit, observation_count,
        average_value, minimum_value, maximum_value,
        weather_context_count, weather_context_percentage,
        null::timestamptz as earliest_observation_utc,
        null::timestamptz as latest_observation_utc
    from {{ ref('agg_daily_air_quality') }}
    union all
    select 'location' as mart, location_id, parameter, unit, observation_count,
        average_value, minimum_value, maximum_value,
        weather_context_count, weather_context_percentage,
        earliest_observation_utc, latest_observation_utc
    from {{ ref('agg_location_air_quality') }}
)
select mart, location_id, parameter, unit
from summaries
where observation_count <= 0
    or minimum_value > maximum_value
    or weather_context_count < 0 or weather_context_count > observation_count
    or weather_context_percentage < 0 or weather_context_percentage > 100
    or earliest_observation_utc > latest_observation_utc
