"""One serial pipeline; install AirAtlas .[dev] alongside Airflow in WSL2/Linux.

Set AIRATLAS_PROJECT_ROOT on task workers and configure their environment secrets.
Point Airflow's DAG folder here; keep its metadata separate from the warehouse.
Do not run independent CLI rebuilds concurrently with this DAG.
"""

from datetime import UTC, datetime, timedelta

from airflow.sdk import DAG, Param, get_current_context, task
from airflow.timetables.interval import CronDataIntervalTimetable

with DAG(
    dag_id="airatlas_pipeline",
    schedule=CronDataIntervalTimetable("0 0 * * *", timezone="UTC"),
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    params={
        "run_mode": Param("incremental", enum=["historical", "incremental"]),
        "date_from": Param(
            None,
            type=["null", "string"],
            format="date",
            description="Historical start date.",
        ),
        "date_to": Param(
            None,
            type=["null", "string"],
            format="date",
            description="Historical end date, strictly later than start.",
        ),
        "checkpoint": Param(
            None,
            type=["null", "string"],
            format="date-time",
            description="Required for manual incremental runs; timezone-aware start.",
        ),
        "datetime_to": Param(
            None,
            type=["null", "string"],
            format="date-time",
            description="Required for manual incremental runs; later timezone-aware end.",
        ),
        "location_id": Param(
            None,
            type=["null", "integer"],
            minimum=1,
            description="Optional approved MVP ID; limits acquisition only.",
        ),
    },
) as dag:

    @task(retries=0, multiple_outputs=False)
    def validate_run_config():
        from airatlas.orchestration.commands import validate_run_config as validate

        context = get_current_context()
        return validate(
            context["params"],
            context.get("data_interval_start"),
            context.get("data_interval_end"),
            manual=context["dag_run"].run_type == "manual",
        )

    @task(do_xcom_push=False)
    def execute_stage(stage, config):
        from airatlas.orchestration.commands import run_stage

        run_stage(stage, config)

    config = validate_run_config()
    acquire = execute_stage.override(task_id="acquire_air_quality")(
        "acquire_air_quality", config
    )
    process = execute_stage.override(task_id="process_air_quality")(
        "process_air_quality", config
    )
    curate = execute_stage.override(task_id="build_curated_air_quality")(
        "build_curated_air_quality", config
    )
    enrich = execute_stage.override(task_id="enrich_air_quality_weather")(
        "enrich_air_quality_weather", config
    )
    warehouse = execute_stage.override(task_id="load_postgres_warehouse")(
        "load_postgres_warehouse", config
    )
    analytics = execute_stage.override(task_id="build_dbt_analytics")(
        "build_dbt_analytics", config
    )
    # Config XCom dependencies also require validation before every stage.
    acquire >> process >> curate >> enrich >> warehouse >> analytics
