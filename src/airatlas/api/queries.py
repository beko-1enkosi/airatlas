"""Explicit mart projections. Filters are values; schema names are quoted identifiers.

Summary is a weighted roll-up of existing location mart statistics, by unit.
Trend/weather/comparison endpoints return dbt metrics without recomputing them.
"""

import os

from psycopg import sql

from airatlas.api.database import query


def statement(template):
    schema = os.environ.get("AIRATLAS_DBT_SCHEMA", "airatlas_analytics") + "_marts"
    return sql.SQL(template).format(marts=sql.Identifier(schema))


def summary():
    totals = query(
        statement("""SELECT count(DISTINCT location_id) AS monitored_locations,
        COALESCE(sum(observation_count), 0) AS observation_count,
        100.0 * sum(weather_context_count) / NULLIF(sum(observation_count), 0)
            AS weather_coverage,
        min(earliest_observation_utc) AS earliest_observation,
        max(latest_observation_utc) AS latest_observation
        FROM {marts}.agg_location_air_quality""")
    )[0]
    # Never average pollutant values across different units, or average averages
    # without weighting by their original observation counts.
    totals["averages"] = query(
        statement("""SELECT parameter, unit,
        sum(average_value * observation_count) / NULLIF(sum(observation_count), 0)
            AS average_value,
        sum(observation_count) AS observation_count
        FROM {marts}.agg_location_air_quality
        GROUP BY parameter, unit ORDER BY parameter, unit""")
    )
    return totals


def locations():
    return query(
        statement("""SELECT l.location_id, l.location_name,
        l.latitude, l.longitude,
        ARRAY(SELECT DISTINCT f.parameter FROM {marts}.agg_location_air_quality f
            WHERE f.location_id = l.location_id ORDER BY f.parameter) AS parameters
        FROM airatlas.locations l ORDER BY l.location_name NULLS LAST, l.location_id""")
    )


OBSERVATION_FIELDS = """sensor_id, parameter, unit, value, datetime_from_utc,
    datetime_to_utc, has_weather_context, weather_hour_utc, temperature_2m_c,
    relative_humidity_2m_pct, precipitation_mm, wind_speed_10m_kmh, weather_source"""


def location_detail(location_id):
    rows = query(
        """SELECT location_id, location_name, latitude, longitude
        FROM airatlas.locations WHERE location_id = %s""",
        (location_id,),
    )
    if not rows:
        return None
    result = rows[0]
    result["latest"] = query(
        statement(
            "SELECT DISTINCT ON (parameter, unit) "
            + OBSERVATION_FIELDS
            + """
        FROM {marts}.fct_air_quality_observations WHERE location_id = %s
        ORDER BY parameter, unit, datetime_to_utc DESC, datetime_from_utc DESC,
            sensor_id ASC"""
        ),
        (location_id,),
    )
    result["recent"] = query(
        statement(
            "SELECT "
            + OBSERVATION_FIELDS
            + """ FROM {marts}.fct_air_quality_observations
        WHERE location_id = %s ORDER BY datetime_to_utc DESC, parameter, unit,
            sensor_id, datetime_from_utc DESC LIMIT 20"""
        ),
        (location_id,),
    )
    return result


def series(kind, parameter, location_id, date_from, date_to, limit):
    # Both choices are internal constants, never user-supplied table names.
    if kind == "trends":
        table = "agg_daily_air_quality"
        fields = """average_value, minimum_value, maximum_value,
            weather_context_count, weather_context_percentage"""
    else:
        table = "agg_pollution_weather"
        fields = """average_pollution_value, average_temperature_2m_c,
            average_relative_humidity_2m_pct, average_precipitation_mm,
            average_wind_speed_10m_kmh, temperature_observation_count,
            humidity_observation_count, precipitation_observation_count,
            wind_observation_count"""
    # Default period ends at the latest stored observation, not today's clock.
    # Bound output and explicitly report truncation instead of claiming completeness.
    rows = query(
        statement(
            """WITH bounds AS (
        SELECT COALESCE(%s::date, max(measurement_date_utc)) AS end_date
        FROM {marts}.fct_air_quality_observations
    ) SELECT measurement_date_utc, location_id, location_name, parameter, unit,
        observation_count, """
            + fields
            + " FROM {marts}."
            + table
            + """, bounds
        WHERE parameter = %s AND (%s::bigint IS NULL OR location_id = %s)
        AND measurement_date_utc >= COALESCE(%s::date, bounds.end_date - 89)
        AND measurement_date_utc <= bounds.end_date
        ORDER BY measurement_date_utc, location_id, parameter, unit LIMIT %s"""
        ),
        (date_to, parameter, location_id, location_id, date_from, limit + 1),
    )
    return {"rows": rows[:limit], "truncated": len(rows) > limit, "limit": limit}


def comparison(parameter):
    return query(
        statement("""SELECT location_id, location_name, parameter, unit,
        observation_count, average_value, minimum_value, maximum_value,
        earliest_observation_utc, latest_observation_utc,
        weather_context_count, weather_context_percentage
        FROM {marts}.agg_location_air_quality WHERE parameter = %s
        ORDER BY unit, location_name NULLS LAST, location_id"""),
        (parameter,),
    )


def data_health():
    # Error text and source file paths are deliberately not exposed to the browser.
    runs = query("""SELECT run_id, run_mode, requested_start, requested_end,
        location_id, status, current_stage, failed_stage, started_at, finished_at,
        observations_loaded FROM airatlas.pipeline_runs
        WHERE dag_id = 'airatlas_pipeline'
        ORDER BY started_at DESC, run_id DESC LIMIT 1""")
    return {"latest_run": runs[0] if runs else None, "summary": summary()}
