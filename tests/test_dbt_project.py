"""Static contracts between dbt declarations and the Python warehouse schema.

Actual Jinja/project validation belongs to `dbt parse`, not a custom parser here.
"""

from pathlib import Path

import yaml

from airatlas.warehouse.schema import LOCATION_COLUMNS, OBSERVATION_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
DBT = ROOT / "dbt"


def read_yaml(relative):
    return yaml.safe_load((DBT / relative).read_text(encoding="utf-8"))


def test_source_columns_match_warehouse():
    source = read_yaml("models/staging/_sources.yml")["sources"][0]
    assert source["name"] == "airatlas_warehouse"
    assert source["schema"] == "airatlas"
    assert source["database"] == "{{ target.database }}"
    assert "freshness" not in source and "loaded_at_field" not in source
    tables = {table["name"]: table for table in source["tables"]}
    for name, expected in [
        ("locations", LOCATION_COLUMNS),
        ("observations", OBSERVATION_COLUMNS),
    ]:
        columns = tables[name]["columns"]
        assert {column["name"] for column in columns} == set(expected)
        assert all(column.get("description") for column in columns)


def test_models_preserve_schema_and_optional_weather():
    staging = read_yaml("models/staging/_staging.yml")["models"]
    intermediate = read_yaml("models/intermediate/_intermediate.yml")["models"]
    models = {model["name"]: model for model in staging + intermediate}
    assert set(models) == {
        "stg_locations",
        "stg_observations",
        "int_air_quality_weather",
    }
    assert {column["name"] for column in models["stg_locations"]["columns"]} == set(
        LOCATION_COLUMNS
    )
    for name in ("stg_observations", "int_air_quality_weather"):
        columns = {column["name"]: column for column in models[name]["columns"]}
        assert set(OBSERVATION_COLUMNS) <= columns.keys()
        assert all(column.get("description") for column in columns.values())
        for optional in (
            "weather_source",
            "temperature_2m_c",
            "relative_humidity_2m_pct",
            "precipitation_mm",
            "wind_speed_10m_kmh",
            "latitude",
            "longitude",
        ):
            assert "not_null" not in columns[optional].get("data_tests", [])
    assert "has_weather_context" in {
        column["name"] for column in intermediate[0]["columns"]
    }


def test_profile_is_environment_based_and_models_are_separate_views():
    project = read_yaml("dbt_project.yml")
    assert project["profile"] == project["name"] == "airatlas_analytics"
    profile = read_yaml("profiles.yml")[project["profile"]]["outputs"]["dev"]
    for field, environment in {
        "host": "AIRATLAS_DB_HOST",
        "port": "AIRATLAS_DB_PORT",
        "dbname": "AIRATLAS_DB_NAME",
        "user": "AIRATLAS_DB_USER",
        "password": "AIRATLAS_DB_PASSWORD",
        "schema": "AIRATLAS_DBT_SCHEMA",
    }.items():
        assert "env_var(" in profile[field] and environment in profile[field]
    assert profile["user"] == "{{ env_var('AIRATLAS_DB_USER', '') }}"
    assert profile["password"] == "{{ env_var('AIRATLAS_DB_PASSWORD', '') }}"
    settings = project["models"][project["name"]]
    assert settings["+materialized"] == "view"
    assert settings["staging"]["+schema"] == "staging"
    assert settings["intermediate"]["+schema"] == "intermediate"
    assert settings["marts"]["+schema"] == "marts"
    assert settings["marts"]["+materialized"] == "table"


def test_marts_are_documented_and_use_model_dependencies():
    models = read_yaml("models/marts/_marts.yml")["models"]
    expected = {
        "fct_air_quality_observations",
        "agg_daily_air_quality",
        "agg_location_air_quality",
        "agg_pollution_weather",
    }
    assert {model["name"] for model in models} == expected
    assert {path.stem for path in (DBT / "models/marts").glob("*.sql")} == expected
    for model in models:
        assert model["description"].startswith("One row per")
        assert all(column.get("description") for column in model["columns"])
        sql = (DBT / "models/marts" / (model["name"] + ".sql")).read_text()
        dependency = (
            "int_air_quality_weather"
            if model["name"] == "fct_air_quality_observations"
            else "fct_air_quality_observations"
        )
        assert "ref('" + dependency + "')" in sql
        assert "source(" not in sql and "airatlas." not in sql


def test_fact_retains_intermediate_columns_and_nullable_weather():
    intermediate = read_yaml("models/intermediate/_intermediate.yml")["models"][0]
    fact = read_yaml("models/marts/_marts.yml")["models"][0]
    assert fact["columns"] == intermediate["columns"]
    for column in fact["columns"]:
        if column["name"] in {"weather_source", "temperature_2m_c", "precipitation_mm"}:
            assert "not_null" not in column.get("data_tests", [])


def test_dbt_generated_artifacts_are_ignored():
    import subprocess

    paths = [
        "dbt/target/manifest.json",
        "dbt/logs/dbt.log",
        "dbt/dbt_packages/pkg/file.sql",
    ]
    result = subprocess.run(
        ["git", "check-ignore", *paths],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert set(result.stdout.splitlines()) == set(paths)
