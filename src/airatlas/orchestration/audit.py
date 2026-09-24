"""One orchestration-owned PostgreSQL summary per Airflow DAG/run identity.

No task history or exception text is stored. Invalid configurations do not create
rows: they have no validated request window. Airflow remains their source of truth.
"""

from datetime import UTC, datetime

import psycopg

from airatlas.orchestration.commands import SCRIPTS
from airatlas.warehouse.loader import database_url

STAGES = ("validate_run_config", "acquire_air_quality", *SCRIPTS, "build_dbt_analytics")
FAILURE_SUMMARY = "Pipeline failed; inspect Airflow task and callback logs."
CREATE_TABLE = """CREATE TABLE IF NOT EXISTS airatlas.pipeline_runs (
    dag_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    run_mode TEXT NOT NULL CHECK (run_mode IN ('historical', 'incremental')),
    requested_start TIMESTAMPTZ NOT NULL,
    requested_end TIMESTAMPTZ NOT NULL CHECK (requested_end > requested_start),
    location_id BIGINT CHECK (location_id > 0),
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    current_stage TEXT NOT NULL,
    failed_stage TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    observations_loaded BIGINT CHECK (observations_loaded >= 0),
    error_summary VARCHAR(160),
    PRIMARY KEY (dag_id, run_id)
)"""
START_RUN = """INSERT INTO airatlas.pipeline_runs
    (dag_id, run_id, run_mode, requested_start, requested_end, location_id,
     status, current_stage)
    VALUES (%s, %s, %s, %s, %s, %s, 'running', 'validate_run_config')
    ON CONFLICT (dag_id, run_id) DO NOTHING"""
UPDATE_STAGE = """UPDATE airatlas.pipeline_runs SET current_stage = %s,
    status = 'running', failed_stage = NULL, finished_at = NULL, error_summary = NULL,
    observations_loaded = CASE WHEN %s = 'build_dbt_analytics'
        THEN observations_loaded ELSE NULL END
    WHERE dag_id = %s AND run_id = %s"""
STORE_COUNT = """UPDATE airatlas.pipeline_runs SET observations_loaded = %s
    WHERE dag_id = %s AND run_id = %s AND status = 'running'"""
SUCCEED = """UPDATE airatlas.pipeline_runs SET status = 'succeeded',
    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP), failed_stage = NULL,
    error_summary = NULL
    WHERE dag_id = %s AND run_id = %s AND status IN ('running', 'succeeded')"""
FAIL = """UPDATE airatlas.pipeline_runs SET status = 'failed',
    failed_stage = COALESCE(%s, current_stage),
    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP), error_summary = %s
    WHERE dag_id = %s AND run_id = %s AND status IN ('running', 'failed')"""


class AuditError(RuntimeError):
    """Audit access failed; public messages never contain database details."""


def _write(statement, parameters=(), *, require_row=True):
    dsn = database_url()
    try:
        with psycopg.connect(dsn, autocommit=False, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE SCHEMA IF NOT EXISTS airatlas")
                cursor.execute(CREATE_TABLE)
                if statement is not None:
                    cursor.execute(statement, parameters)
                    if require_row and cursor.rowcount != 1:
                        raise AuditError(
                            "Audit run is not initialized or its state conflicts with this update."
                        )
    except psycopg.Error:
        raise AuditError(
            "Pipeline audit write failed; check database availability and permissions."
        ) from None


def ensure_audit_table():
    _write(None)


def start_run(dag_id, run_id, config):
    start, end = (datetime.fromisoformat(config[key]) for key in ("start", "end"))
    if config["run_mode"] == "historical":
        # Date-only CLI boundaries represent midnight UTC, without shifting days.
        start, end = start.replace(tzinfo=UTC), end.replace(tzinfo=UTC)
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("Audit window requires increasing timezone-aware boundaries.")
    _write(
        START_RUN,
        (
            dag_id,
            run_id,
            config["run_mode"],
            start.astimezone(UTC),
            end.astimezone(UTC),
            config["location_id"],
        ),
        require_row=False,
    )


def update_stage(dag_id, run_id, stage):
    if stage not in STAGES:
        raise ValueError("Unknown pipeline audit stage.")
    _write(UPDATE_STAGE, (stage, stage, dag_id, run_id))


def store_observation_count(dag_id, run_id, count):
    if type(count) is not int or not 0 <= count <= 2**63 - 1:
        raise ValueError("Observation count must be a non-negative BIGINT.")
    _write(STORE_COUNT, (count, dag_id, run_id))


def mark_succeeded(dag_id, run_id):
    _write(SUCCEED, (dag_id, run_id))


def mark_failed(dag_id, run_id, stage=None):
    # The stored stage is authoritative for this serial DAG. A DAG callback's
    # selected task can instead be a downstream upstream_failed task.
    # Never persist context['exception'], command output, DSNs or tracebacks.
    if stage is not None and stage not in STAGES:
        raise ValueError("Unknown pipeline audit stage.")
    _write(FAIL, (stage, FAILURE_SUMMARY, dag_id, run_id))


def dag_succeeded(context):
    run = context["dag_run"]
    mark_succeeded(run.dag_id, run.run_id)


def dag_failed(context):
    run = context["dag_run"]
    task = context.get("task_instance")
    stage = getattr(task, "task_id", None)
    # Airflow 3.3 selects a failed task on ordinary DAG failure. Only trust it
    # when explicitly failed; timeout/deadlock contexts fall back to stored stage.
    if getattr(task, "state", None) != "failed" or stage not in STAGES:
        stage = None
    mark_failed(run.dag_id, run.run_id, stage)
