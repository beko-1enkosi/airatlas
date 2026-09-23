"""Explicit PostgreSQL DDL and column mappings; no migrations or ORM."""

LOCATION_COLUMNS = (
    "location_id",
    "location_name",
    "latitude",
    "longitude",
    "weather_latitude",
    "weather_longitude",
)
OBSERVATION_TYPES = {
    "location_id": "BIGINT NOT NULL REFERENCES airatlas.locations(location_id)",
    "location_name": "TEXT",
    "sensor_id": "BIGINT NOT NULL CHECK (sensor_id > 0)",
    "parameter": "TEXT NOT NULL CHECK (parameter IN ('pm25', 'pm10'))",
    "parameter_id": "BIGINT",
    "unit": "TEXT NOT NULL",
    "value": "DOUBLE PRECISION NOT NULL",
    "period_label": "TEXT",
    "period_interval": "TEXT",
    "datetime_from_utc": "TIMESTAMPTZ NOT NULL",
    "datetime_to_utc": "TIMESTAMPTZ NOT NULL",
    "datetime_from_local": "TEXT",
    "datetime_to_local": "TEXT",
    "measurement_date_utc": "DATE NOT NULL",
    "latitude": "DOUBLE PRECISION",
    "longitude": "DOUBLE PRECISION",
    "source": "TEXT NOT NULL",
    "source_file": "TEXT",
    "retrieval_datetime_from": "TEXT",
    "retrieval_datetime_to": "TEXT",
    "weather_hour_utc": "TIMESTAMPTZ NOT NULL",
    "temperature_2m_c": "DOUBLE PRECISION",
    "relative_humidity_2m_pct": "DOUBLE PRECISION",
    "precipitation_mm": "DOUBLE PRECISION",
    "wind_speed_10m_kmh": "DOUBLE PRECISION",
    "weather_source": "TEXT",
    "weather_latitude": "DOUBLE PRECISION",
    "weather_longitude": "DOUBLE PRECISION",
}
OBSERVATION_COLUMNS = tuple(OBSERVATION_TYPES)

SCHEMA_STATEMENTS = (
    "CREATE SCHEMA IF NOT EXISTS airatlas",
    """CREATE TABLE IF NOT EXISTS airatlas.locations (
        location_id BIGINT PRIMARY KEY CHECK (location_id > 0),
        location_name TEXT,
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        weather_latitude DOUBLE PRECISION,
        weather_longitude DOUBLE PRECISION
    )""",
    "CREATE TABLE IF NOT EXISTS airatlas.observations (\n"
    + ",\n".join(f"{column} {dtype}" for column, dtype in OBSERVATION_TYPES.items())
    + """,
        CONSTRAINT observations_natural_key UNIQUE (
            location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc
        ),
        CONSTRAINT observations_valid_period CHECK (datetime_to_utc > datetime_from_utc)
    )""",
    "CREATE INDEX IF NOT EXISTS observations_location_time_idx ON airatlas.observations (location_id, datetime_to_utc)",
    "CREATE INDEX IF NOT EXISTS observations_parameter_time_idx ON airatlas.observations (parameter, datetime_to_utc)",
    "CREATE INDEX IF NOT EXISTS observations_date_idx ON airatlas.observations (measurement_date_utc)",
)

# Column and table names are application constants, never supplied by the caller.
INSERT_LOCATIONS = f"INSERT INTO airatlas.locations ({', '.join(LOCATION_COLUMNS)}) VALUES ({', '.join(['%s'] * len(LOCATION_COLUMNS))})"
INSERT_OBSERVATIONS = f"INSERT INTO airatlas.observations ({', '.join(OBSERVATION_COLUMNS)}) VALUES ({', '.join(['%s'] * len(OBSERVATION_COLUMNS))})"

VALIDATE_SQL = """SELECT
    (SELECT count(*) FROM airatlas.observations),
    (SELECT count(*) FROM airatlas.locations),
    (SELECT count(*) FROM (
        SELECT location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc
        FROM airatlas.observations
        GROUP BY location_id, sensor_id, parameter, datetime_from_utc, datetime_to_utc
        HAVING count(*) > 1
    ) AS duplicate_keys),
    (SELECT count(*) FROM airatlas.observations WHERE parameter NOT IN ('pm25', 'pm10') OR parameter IS NULL),
    (SELECT count(*) FROM airatlas.observations AS o
        LEFT JOIN airatlas.locations AS l ON l.location_id = o.location_id
        WHERE l.location_id IS NULL)
"""


def ensure_schema(cursor):
    for statement in SCHEMA_STATEMENTS:
        cursor.execute(statement)
