"""Offline configuration/CLI contracts; no Airflow installation or database needed."""

import ast
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from airatlas.orchestration import commands

ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 2, tzinfo=UTC)


@pytest.fixture(autouse=True)
def root_environment(monkeypatch):
    monkeypatch.setenv("AIRATLAS_PROJECT_ROOT", str(ROOT))


def historical(**changes):
    return {
        "run_mode": "historical",
        "date_from": "2026-01-01",
        "date_to": "2026-01-02",
        **changes,
    }


def test_historical_command_and_location():
    config = commands.validate_run_config(historical(location_id=225448))
    assert commands.build_command("acquire_air_quality", config) == [
        sys.executable,
        "scripts/backfill_openaq_measurements.py",
        "--date-from",
        "2026-01-01",
        "--date-to",
        "2026-01-02",
        "--location-id",
        "225448",
    ]


def test_scheduled_interval_and_no_location():
    config = commands.validate_run_config({}, START, END)
    assert commands.build_command("acquire_air_quality", config) == [
        sys.executable,
        "scripts/ingest_incremental_openaq.py",
        "--checkpoint",
        "2026-01-01T00:00:00Z",
        "--datetime-to",
        "2026-01-02T00:00:00Z",
    ]


def test_manual_incremental_normalizes_offset_and_whitelists_output():
    config = commands.validate_run_config(
        {
            "checkpoint": "2026-01-01T02:00:00+02:00",
            "datetime_to": "2026-01-01T03:00:00+02:00",
            "unexpected": "must not reach XCom",
        },
        manual=True,
    )
    assert config == {
        "run_mode": "incremental",
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-01T01:00:00Z",
        "location_id": None,
    }


@pytest.mark.parametrize(
    "start,end",
    [
        (None, None),
        ("bad", "2026-01-02"),
        ("2026-01-01", "2026-01-01"),
        ("2026-01-03", "2026-01-02"),
        ("2026-02-30", "2026-03-02"),
    ],
)
def test_invalid_historical_range(start, end):
    with pytest.raises(ValueError):
        commands.validate_run_config(historical(date_from=start, date_to=end))


@pytest.mark.parametrize(
    "start,end",
    [
        (None, None),
        (None, "2026-01-02T00:00:00Z"),
        ("2026-01-01T00:00:00", "2026-01-02T00:00:00Z"),
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        ("2026-01-03T00:00:00Z", "2026-01-02T00:00:00Z"),
    ],
)
def test_invalid_manual_incremental_range(start, end):
    with pytest.raises(ValueError):
        commands.validate_run_config(
            {"checkpoint": start, "datetime_to": end}, manual=True
        )


@pytest.mark.parametrize(
    "start,end",
    [(None, None), (START, START), (END, START), (START.replace(tzinfo=None), END)],
)
def test_invalid_scheduled_interval(start, end):
    with pytest.raises(ValueError):
        commands.validate_run_config({}, start, end)


@pytest.mark.parametrize("location_id", [0, -1, True, "225448", 1.5, 999999999])
def test_invalid_or_unapproved_location(location_id):
    with pytest.raises(ValueError):
        commands.validate_run_config(historical(location_id=location_id))


@pytest.mark.parametrize(
    "params,manual",
    [
        ({"run_mode": "unknown"}, False),
        (historical(checkpoint="2026-01-01T00:00:00Z"), False),
        ({"date_from": "2026-01-01"}, False),
        (
            {
                "checkpoint": "2026-01-01T00:00:00Z",
                "datetime_to": "2026-01-02T00:00:00Z",
            },
            False,
        ),
        ({}, True),
    ],
)
def test_invalid_mode_or_ambiguous_window(params, manual):
    with pytest.raises(ValueError):
        commands.validate_run_config(params, START, END, manual=manual)


@pytest.mark.parametrize("value", [None, "", "relative/path"])
def test_missing_or_relative_root(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("AIRATLAS_PROJECT_ROOT")
    else:
        monkeypatch.setenv("AIRATLAS_PROJECT_ROOT", value)
    with pytest.raises(ValueError, match="AIRATLAS_PROJECT_ROOT"):
        commands.project_root()


def test_root_requires_actual_scripts(monkeypatch, tmp_path):
    monkeypatch.setenv("AIRATLAS_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="required project files"):
        commands.project_root()


@pytest.mark.parametrize("stage", list(commands.SCRIPTS))
def test_downstream_commands(stage):
    assert commands.build_command(stage, {}) == [sys.executable, f"scripts/{stage}.py"]
    assert (ROOT / "scripts" / f"{stage}.py").is_file()


def test_dbt_command():
    command = commands.build_command("build_dbt_analytics", {})
    assert Path(command[0]).parent == Path(sys.executable).parent
    assert Path(command[0]).stem == "dbt"
    assert command[1:] == ["build", "--project-dir", "dbt", "--profiles-dir", "dbt"]


def test_subprocess_inherits_environment_and_propagates_failure(monkeypatch):
    calls = []

    def fail(argv, **kwargs):
        calls.append((argv, kwargs))
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(commands.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        commands.run_stage("process_air_quality", {})
    assert calls == [
        (
            [sys.executable, "scripts/process_air_quality.py"],
            {"cwd": ROOT.resolve(), "check": True},
        )
    ]


def test_stage_returns_no_dataset(monkeypatch):
    monkeypatch.setattr(commands.subprocess, "run", lambda *a, **k: object())
    assert commands.run_stage("process_air_quality", {}) is None


def test_dag_static_contract():
    path = ROOT / "airflow/dags/airatlas_pipeline.py"
    text = path.read_text()
    tree = ast.parse(text)  # Python syntax only; not an Airflow import/parse.
    dag = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "DAG"
    )
    kwargs = {k.arg: k.value for k in dag.keywords}
    assert ast.literal_eval(kwargs["dag_id"]) == "airatlas_pipeline"
    assert ast.literal_eval(kwargs["max_active_runs"]) == 1
    assert ast.literal_eval(kwargs["catchup"]) is False
    assert 'CronDataIntervalTimetable("0 0 * * *", timezone="UTC")' in text
    assert "from airflow.sdk import" in text and "schedule_interval" not in text
    for task in [
        "validate_run_config",
        "acquire_air_quality",
        *commands.SCRIPTS,
        "build_dbt_analytics",
    ]:
        assert task in text
    assert "acquire >> process >> curate >> enrich >> warehouse >> analytics" in text
    assert "@task(do_xcom_push=False)" in text
    assert '"retries": 1' in text and "timedelta(minutes=5)" in text
    assert "all_done" not in text and "C:\\" not in text


def test_airflow_is_isolated_and_generated_files_ignored():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = (
        project["project"]["dependencies"]
        + project["project"]["optional-dependencies"]["dev"]
    )
    assert not any("apache-airflow" in dep for dep in deps)
    assert "apache-airflow==3.3.2" in (ROOT / "airflow/requirements.txt").read_text()
    ignored = [
        "airflow/airflow.cfg",
        "airflow/airflow.db",
        "airflow/logs/run.log",
        "airflow/simple_auth_manager_passwords.json.generated",
        "dbt/target/manifest.json",
    ]
    result = subprocess.run(
        ["git", "check-ignore", *ignored],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert set(result.stdout.splitlines()) == set(ignored)
