-- Separate relation labels test all observation boundaries without mixing their keys.
with observation_keys as (
    select
        'warehouse' as relation_name,
        location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc
    from {{ source('airatlas_warehouse', 'observations') }}

    union all

    select
        'intermediate' as relation_name,
        location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc
    from {{ ref('int_air_quality_weather') }}

    union all

    select
        'fact' as relation_name,
        location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc
    from {{ ref('fct_air_quality_observations') }}
)
select
    relation_name,
    location_id,
    sensor_id,
    parameter,
    datetime_from_utc,
    datetime_to_utc,
    count(*) as record_count
from observation_keys
group by
    relation_name, location_id, sensor_id, parameter,
    datetime_from_utc, datetime_to_utc
having count(*) > 1
