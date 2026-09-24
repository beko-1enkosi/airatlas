"""Audit contracts using a transactional fake; no live PostgreSQL or Airflow."""

import copy
from datetime import UTC, datetime
from types import SimpleNamespace

import psycopg
import pytest

from airatlas.orchestration import audit

DAG = "airatlas_pipeline"
RUN = "manual__audit_test"
CONFIG = {
    "run_mode": "historical",
    "start": "2026-09-01",
    "end": "2026-09-02",
    "location_id": None,
}


class Database:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.commits = self.rollbacks = 0
        self.rowcount = 0

    def __enter__(self):
        self.before = copy.deepcopy(self.rows)
        return self

    def __exit__(self, kind, *args):
        if kind:
            self.rows = self.before
            self.rollbacks += 1
        else:
            self.commits += 1

    def cursor(self):
        from contextlib import nullcontext

        return nullcontext(self)

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        self.rowcount = 0
        if sql.startswith("CREATE"):
            return
        if sql == audit.START_RUN:
            dag, run, mode, start, end, location = params
            key = (dag, run)
            if key not in self.rows:
                self.rows[key] = dict(
                    run_mode=mode,
                    requested_start=start,
                    requested_end=end,
                    location_id=location,
                    status="running",
                    current_stage="validate_run_config",
                    failed_stage=None,
                    started_at=datetime.now(UTC),
                    finished_at=None,
                    observations_loaded=None,
                    error_summary=None,
                )
                self.rowcount = 1
            return
        key = tuple(params[-2:])
        if key not in self.rows:
            return
        row = self.rows[key]
        self.rowcount = 1
        if sql == audit.UPDATE_STAGE:
            row.update(
                status="running",
                current_stage=params[0],
                failed_stage=None,
                finished_at=None,
                error_summary=None,
            )
            if params[0] != "build_dbt_analytics":
                row["observations_loaded"] = None
        elif sql == audit.STORE_COUNT:
            row["observations_loaded"] = params[0]
        elif sql in (audit.SUCCEED, audit.FAIL):
            row["finished_at"] = row["finished_at"] or datetime.now(UTC)
            row["status"] = "succeeded" if sql == audit.SUCCEED else "failed"
            row["failed_stage"] = (
                None if sql == audit.SUCCEED else (params[0] or row["current_stage"])
            )
            row["error_summary"] = None if sql == audit.SUCCEED else params[1]
        else:
            pytest.fail("Unexpected audit SQL")


@pytest.fixture
def database(monkeypatch):
    db = Database()
    monkeypatch.setenv(
        "AIRATLAS_DATABASE_URL", "postgresql://USER:TEST_PLACEHOLDER@localhost/airatlas"
    )
    monkeypatch.setattr(audit.psycopg, "connect", lambda *a, **k: db)
    return db


def test_schema_and_start_idempotency(database):
    audit.ensure_audit_table()
    audit.start_run(DAG, RUN, CONFIG)
    before = copy.deepcopy(database.rows)
    audit.start_run(DAG, RUN, CONFIG)
    assert database.rows == before
    row = database.rows[DAG, RUN]
    assert row["location_id"] is None and row["status"] == "running"
    assert row["requested_start"] == datetime(2026, 9, 1, tzinfo=UTC)
    assert row["requested_end"] == datetime(2026, 9, 2, tzinfo=UTC)
    assert row["started_at"].tzinfo and row["finished_at"] is None
    assert "PRIMARY KEY (dag_id, run_id)" in audit.CREATE_TABLE
    assert "'running', 'succeeded', 'failed'" in audit.CREATE_TABLE
    assert "VARCHAR(160)" in audit.CREATE_TABLE
    assert "REFERENCES" not in audit.CREATE_TABLE  # Survives dimension refreshes.


def test_incremental_window_and_location(database):
    config = dict(
        CONFIG,
        run_mode="incremental",
        start="2026-09-01T02:00:00+02:00",
        end="2026-09-01T03:00:00+02:00",
        location_id=225448,
    )
    audit.start_run(DAG, RUN, config)
    row = database.rows[DAG, RUN]
    assert row["location_id"] == 225448 and row["run_mode"] == "incremental"
    assert row["requested_start"] == datetime(2026, 9, 1, tzinfo=UTC)
    assert row["requested_end"] == datetime(2026, 9, 1, 1, tzinfo=UTC)


def test_retry_and_success_preserve_one_run(database):
    audit.start_run(DAG, RUN, CONFIG)
    started = database.rows[DAG, RUN]["started_at"]
    for _ in range(2):
        audit.update_stage(DAG, RUN, "load_postgres_warehouse")
    audit.store_observation_count(DAG, RUN, 6)
    audit.update_stage(DAG, RUN, "build_dbt_analytics")
    audit.dag_succeeded({"dag_run": SimpleNamespace(dag_id=DAG, run_id=RUN)})
    first = copy.deepcopy(database.rows[DAG, RUN])
    audit.mark_succeeded(DAG, RUN)
    assert database.rows[DAG, RUN] == first
    assert first["status"] == "succeeded" and first["finished_at"] is not None
    assert first["observations_loaded"] == 6 and first["started_at"] == started
    assert len(database.rows) == 1


@pytest.mark.parametrize(
    "state,expected",
    [("failed", "process_air_quality"), ("upstream_failed", "acquire_air_quality")],
)
def test_failure_context_and_safe_summary(database, state, expected):
    audit.start_run(DAG, RUN, CONFIG)
    audit.update_stage(DAG, RUN, "acquire_air_quality")
    context = {
        "dag_run": SimpleNamespace(dag_id=DAG, run_id=RUN),
        "task_instance": SimpleNamespace(task_id="process_air_quality", state=state),
        "exception": RuntimeError("postgresql://user:VERY_SECRET@host/db " * 1000),
    }
    audit.dag_failed(context)
    row = database.rows[DAG, RUN]
    assert row["status"] == "failed" and row["failed_stage"] == expected
    assert row["finished_at"] is not None
    assert row["error_summary"] == audit.FAILURE_SUMMARY
    assert len(row["error_summary"]) <= 160
    assert "VERY_SECRET" not in str(database.calls)
    audit.update_stage(DAG, RUN, "acquire_air_quality")
    assert row["status"] == "running" and row["finished_at"] is None


@pytest.mark.parametrize("count", [-1, True, 1.5, "6", 2**63])
def test_invalid_count_rejected(database, count):
    with pytest.raises(ValueError):
        audit.store_observation_count(DAG, RUN, count)
    assert not database.calls


def test_missing_configuration(monkeypatch):
    monkeypatch.delenv("AIRATLAS_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="AIRATLAS_DATABASE_URL"):
        audit.ensure_audit_table()


def test_database_failure_is_redacted(monkeypatch, database):
    def fail(*args, **kwargs):
        raise psycopg.OperationalError("password=VERY_SECRET")

    monkeypatch.setattr(audit.psycopg, "connect", fail)
    with pytest.raises(audit.AuditError) as error:
        audit.ensure_audit_table()
    assert "VERY_SECRET" not in str(error.value)
    assert error.value.__suppress_context__


def test_missing_initialized_run_fails_clearly(database):
    with pytest.raises(audit.AuditError, match="not initialized"):
        audit.mark_succeeded(DAG, RUN)
    assert database.rollbacks == 1


def test_invalid_stage_is_not_persisted(database):
    with pytest.raises(ValueError, match="Unknown"):
        audit.update_stage(DAG, RUN, "password=VERY_SECRET")
    assert not database.calls
