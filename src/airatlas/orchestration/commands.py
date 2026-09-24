"""Coordinate production CLIs without importing Airflow or moving dataset payloads."""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from airatlas.ingestion.historical_backfill import validate_date_range
from airatlas.ingestion.incremental import normalize_incremental_window
from airatlas.ingestion.measurement_window import load_mvp_config, select_mvp_locations

SCRIPTS = {
    "process_air_quality": "process_air_quality.py",
    "build_curated_air_quality": "build_curated_air_quality.py",
    "enrich_air_quality_weather": "enrich_air_quality_weather.py",
    "load_postgres_warehouse": "load_postgres_warehouse.py",
}


def project_root():
    value = os.environ.get("AIRATLAS_PROJECT_ROOT", "")
    if not value.strip():
        raise ValueError("Set AIRATLAS_PROJECT_ROOT to the AirAtlas repository.")
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise ValueError("AIRATLAS_PROJECT_ROOT must be an absolute directory.")
    required = [
        "config/mvp_locations.json",
        "dbt/dbt_project.yml",
        "dbt/profiles.yml",
        "scripts/backfill_openaq_measurements.py",
        "scripts/ingest_incremental_openaq.py",
        *(f"scripts/{name}" for name in SCRIPTS.values()),
    ]
    if not all((root / name).is_file() for name in required):
        raise ValueError("AIRATLAS_PROJECT_ROOT is missing required project files.")
    return root.resolve()


def validate_run_config(
    params, interval_start=None, interval_end=None, *, manual=False
):
    """Return only tiny, non-secret acquisition configuration for XCom.

    Scheduled windows come from Airflow, not a clock or a durable checkpoint.
    Manual incremental runs require both explicit boundaries. All runs rebuild
    downstream snapshots from the available files, even with a location filter.
    """
    root = project_root()
    mode = params.get("run_mode", "incremental")
    if mode not in {"historical", "incremental"}:
        raise ValueError("run_mode must be historical or incremental.")
    location_id = params.get("location_id")
    if location_id is not None and (type(location_id) is not int or location_id <= 0):
        raise ValueError("location_id must be a positive integer or null.")
    select_mvp_locations(
        load_mvp_config(root / "config/mvp_locations.json"), location_id
    )
    if mode == "historical":
        if (
            params.get("checkpoint") is not None
            or params.get("datetime_to") is not None
        ):
            raise ValueError("Historical mode uses date_from/date_to only.")
        start, end = params.get("date_from"), params.get("date_to")
        validate_date_range(start, end)
    else:
        if params.get("date_from") is not None or params.get("date_to") is not None:
            raise ValueError("Incremental mode uses timestamp boundaries, not dates.")
        if manual:
            start, end = params.get("checkpoint"), params.get("datetime_to")
            if start is None or end is None:
                raise ValueError(
                    "Manual incremental runs require checkpoint and datetime_to."
                )
        else:
            if (
                params.get("checkpoint") is not None
                or params.get("datetime_to") is not None
            ):
                raise ValueError(
                    "Scheduled incremental runs use the Airflow data interval."
                )
            if not isinstance(interval_start, datetime) or not isinstance(
                interval_end, datetime
            ):
                raise ValueError("A timezone-aware Airflow data interval is required.")
            start, end = interval_start.isoformat(), interval_end.isoformat()
        start, end = normalize_incremental_window(start, end)
    return {"run_mode": mode, "start": start, "end": end, "location_id": location_id}


def build_command(stage, config):
    """Build argument arrays only; never put credentials or shell fragments here."""
    if stage == "acquire_air_quality":
        if config["run_mode"] == "historical":
            script, flags = (
                "backfill_openaq_measurements.py",
                ("--date-from", "--date-to"),
            )
        elif config["run_mode"] == "incremental":
            script, flags = (
                "ingest_incremental_openaq.py",
                ("--checkpoint", "--datetime-to"),
            )
        else:
            raise ValueError("Unknown acquisition mode.")
        command = [
            sys.executable,
            f"scripts/{script}",
            flags[0],
            config["start"],
            flags[1],
            config["end"],
        ]
        if config["location_id"] is not None:
            command.extend(["--location-id", str(config["location_id"])])
        return command
    if stage in SCRIPTS:
        return [sys.executable, f"scripts/{SCRIPTS[stage]}"]
    if stage == "build_dbt_analytics":
        executable = Path(sys.executable).with_name(
            "dbt.exe" if os.name == "nt" else "dbt"
        )
        return [
            str(executable),
            "build",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
        ]
    raise ValueError("Unknown pipeline stage.")


def run_stage(stage, config):
    # Environment is inherited, never serialized into Params, argv or XCom.
    # CLI summaries stream to task logs; datasets remain in files/PostgreSQL.
    if stage == "load_postgres_warehouse":
        result = subprocess.run(
            build_command(stage, config),
            cwd=project_root(),
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            count = json.loads(result.stdout)["observations_loaded"]
            if type(count) is not int or not 0 <= count <= 2**63 - 1:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise ValueError(
                "Warehouse returned an invalid observation-count summary."
            ) from None
        return {"observations_loaded": count}
    subprocess.run(build_command(stage, config), cwd=project_root(), check=True)


def run_audited_stage(stage, config, dag_id, run_id):
    from airatlas.orchestration import audit

    audit.update_stage(dag_id, run_id, stage)
    # No exception handler: original pipeline failures reach Airflow unchanged.
    # Final failure is recorded by the DAG callback, after retries are exhausted.
    result = run_stage(stage, config)
    if stage == "load_postgres_warehouse":
        audit.store_observation_count(dag_id, run_id, result["observations_loaded"])
