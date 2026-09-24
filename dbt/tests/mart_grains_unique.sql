with mart_keys as (
    select 'daily' as mart, measurement_date_utc, location_id, parameter, unit
    from {{ ref('agg_daily_air_quality') }}
    union all
    select 'location' as mart, null::date, location_id, parameter, unit
    from {{ ref('agg_location_air_quality') }}
    union all
    select 'weather' as mart, measurement_date_utc, location_id, parameter, unit
    from {{ ref('agg_pollution_weather') }}
)
select mart, measurement_date_utc, location_id, parameter, unit, count(*)
from mart_keys
group by mart, measurement_date_utc, location_id, parameter, unit
having count(*) > 1
