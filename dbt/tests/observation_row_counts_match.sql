-- Thin views and the location left join must preserve the snapshot row count.
with row_counts as (
    select
        (select count(*) from {{ source('airatlas_warehouse', 'observations') }}) as warehouse_rows,
        (select count(*) from {{ ref('stg_observations') }}) as staging_rows,
        (select count(*) from {{ ref('int_air_quality_weather') }}) as intermediate_rows,
        (select count(*) from {{ ref('fct_air_quality_observations') }}) as fact_rows
)
select warehouse_rows, staging_rows, intermediate_rows, fact_rows
from row_counts
where warehouse_rows <> staging_rows or staging_rows <> intermediate_rows
    or intermediate_rows <> fact_rows
