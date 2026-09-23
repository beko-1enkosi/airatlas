"""Build a validated Parquet snapshot from processed CSV, without changing inputs.

Partition dates use the UTC period end. Rebuilds replace this builder's entire
OpenAQ namespace (dataset plus manifest), so stale partitions cannot accumulate.
Run one builder at a time; directory publication is not a concurrent-reader or
power-loss transaction. Ordinary publication failures restore the previous build.
"""

import json
import math
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from airatlas.processing.normalize import COLUMNS, KEY

REQUIRED = {
    "source",
    "location_id",
    "location_name",
    "sensor_id",
    "parameter",
    "unit",
    "value",
    "datetime_from_utc",
    "datetime_to_utc",
}
PARTITIONS = ["parameter", "measurement_date_utc"]
ORDER = PARTITIONS + [
    "datetime_to_utc",
    "location_id",
    "sensor_id",
    "datetime_from_utc",
]
TIMESTAMPS = ["datetime_from_utc", "datetime_to_utc"]
INTEGERS = ["location_id", "sensor_id", "parameter_id"]
NUMBERS = ["value", "latitude", "longitude"]


class CurationInputError(ValueError):
    """Processed input is not suitable for publishing a curated snapshot."""


def load_processed(input_file: Path) -> pd.DataFrame:
    """Restore CSV types explicitly; empty fields are null, literal 'NA' stays text."""
    try:
        frame = pd.read_csv(
            input_file, dtype="string", keep_default_na=False, na_values=[""]
        )
    except (OSError, ValueError) as exc:
        raise CurationInputError(
            f"Cannot read processed CSV: {Path(input_file).name}"
        ) from exc
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise CurationInputError(
            f"Missing required processed columns: {', '.join(sorted(missing))}"
        )
    if frame.empty:
        raise CurationInputError(
            "Processed CSV contains no observations; no curated snapshot was published."
        )
    if not frame["source"].eq("openaq").fillna(False).all():
        raise CurationInputError("Processed source must be openaq.")
    if not frame["parameter"].isin(["pm25", "pm10"]).all():
        raise CurationInputError("Only pm25 and pm10 parameters are supported.")
    if frame["unit"].isna().any() or frame["unit"].str.strip().eq("").any():
        raise CurationInputError(
            "Processed observations require a non-empty source unit."
        )
    for column in INTEGERS:
        if column not in frame:
            continue
        values = []
        for value in frame[column]:
            if pd.isna(value) and column == "parameter_id":
                values.append(None)
            elif (
                isinstance(value, str)
                and value.isascii()
                and value.isdecimal()
                and 0 < int(value) <= 2**63 - 1
            ):
                values.append(int(value))
            else:
                raise CurationInputError(f"Invalid positive integer in {column}.")
        frame[column] = pd.array(values, dtype="Int64")
    for column in NUMBERS:
        if column not in frame:
            continue
        try:
            values = pd.to_numeric(frame[column], errors="raise").astype("Float64")
        except (ValueError, TypeError) as exc:
            raise CurationInputError(f"Invalid numeric values in {column}.") from exc
        if (column == "value" and values.isna().any()) or not all(
            math.isfinite(value) for value in values.dropna()
        ):
            raise CurationInputError(f"Invalid finite numeric values in {column}.")
        frame[column] = values
    for column in TIMESTAMPS:
        values = []
        try:
            for value in frame[column]:
                stamp = pd.Timestamp(value)
                if pd.isna(stamp) or stamp.tzinfo is None:
                    raise ValueError
                values.append(stamp.tz_convert("UTC").as_unit("ns"))
        except (ValueError, TypeError, OverflowError) as exc:
            raise CurationInputError(
                f"{column} requires valid timezone-aware timestamps."
            ) from exc
        frame[column] = pd.to_datetime(values, utc=True)
    if not (frame["datetime_to_utc"] > frame["datetime_from_utc"]).all():
        raise CurationInputError("Measurement period end must be later than its start.")
    if frame.duplicated(KEY).any():
        raise CurationInputError(
            "Duplicate logical observations in processed input; rebuild processing first."
        )
    dates = frame["datetime_to_utc"].dt.strftime("%Y-%m-%d").astype("string")
    if (
        "measurement_date_utc" in frame
        and not frame["measurement_date_utc"].eq(dates).fillna(False).all()
    ):
        raise CurationInputError(
            "Existing measurement_date_utc disagrees with UTC period end."
        )
    frame["measurement_date_utc"] = dates
    columns = [column for column in COLUMNS if column in frame]
    columns += sorted(set(frame.columns) - set(COLUMNS) - {"measurement_date_utc"})
    columns += ["measurement_date_utc"]
    return frame[columns].sort_values(ORDER, kind="stable").reset_index(drop=True)


def _table(frame: pd.DataFrame) -> pa.Table:
    # Explicit Arrow types keep entirely null optional fields typed consistently.
    fields = []
    for column in frame.columns:
        if column in TIMESTAMPS:
            dtype = pa.timestamp("ns", tz="UTC")
        elif column in INTEGERS:
            dtype = pa.int64()
        elif column in NUMBERS:
            dtype = pa.float64()
        else:
            dtype = pa.string()
        fields.append(pa.field(column, dtype))
    return pa.Table.from_pandas(
        frame, schema=pa.schema(fields), preserve_index=False
    ).replace_schema_metadata(None)


def _write_dataset(table: pa.Table, destination: Path) -> None:
    # One fixed filename per deterministically sorted partition; no append mode.
    frame = table.select(PARTITIONS).to_pandas()
    for (parameter, day), indices in frame.groupby(
        PARTITIONS, sort=True
    ).groups.items():
        partition = (
            destination / f"parameter={parameter}" / f"measurement_date_utc={day}"
        )
        partition.mkdir(parents=True)
        pq.write_table(
            table.take(pa.array(list(indices))).drop(PARTITIONS),
            partition / "part-00000.parquet",
            compression="snappy",
        )


def _validate_written(destination: Path, expected: pa.Table) -> None:
    partitioning = ds.partitioning(
        pa.schema([(name, pa.string()) for name in PARTITIONS]), flavor="hive"
    )
    actual = ds.dataset(
        destination, format="parquet", partitioning=partitioning
    ).to_table()
    if set(actual.column_names) != set(expected.column_names):
        raise CurationInputError(
            "Parquet read-back columns differ from processed input."
        )
    for column in TIMESTAMPS:
        if actual.schema.field(column).type != pa.timestamp("ns", tz="UTC"):
            raise CurationInputError(
                "Parquet read-back did not preserve UTC timestamp types."
            )
    actual = actual.select(expected.column_names).sort_by(
        [(column, "ascending") for column in ORDER]
    )
    # Equality verifies counts, values, nulls, parameters, and duplicate absence.
    if not actual.equals(expected, check_metadata=False):
        raise CurationInputError(
            "Parquet read-back differs from validated processed observations."
        )


def _remove_owned(path: Path, output: Path) -> None:
    # Only remove temporary/backup directories allocated inside this output root.
    if (
        path.is_symlink()
        or path.resolve().parent != output
        or not path.name.startswith(".airatlas-curation-")
    ):
        raise CurationInputError(
            "Refusing cleanup outside the owned curation directory."
        )
    if path.exists():
        shutil.rmtree(path)


def build_curated_air_quality(input_file: Path, output_dir: Path) -> dict:
    """Stage, read back, and publish the dataset and manifest together.

    An empty input raises without changing an existing snapshot. The owned
    output_dir/openaq directory must contain only air_quality and its manifest.
    An interrupted directory swap may leave a backup for manual recovery; it is
    never deleted if rollback fails. No raw or processed files are written.
    """
    input_file, output = Path(input_file).resolve(), Path(output_dir).resolve()
    target = output / "openaq"
    repository = Path(__file__).resolve().parents[3]
    protected = [
        input_file.parent,
        repository / "data/raw",
        repository / "data/processed",
    ]
    if any(
        target.is_relative_to(path.resolve()) or path.resolve().is_relative_to(target)
        for path in protected
    ):
        raise CurationInputError(
            "Curated destination must not overlap raw or processed inputs."
        )
    if target.is_symlink() or target.resolve() != target:
        raise CurationInputError(
            "Curated destination must not be a symlink or junction."
        )
    if target.exists() and (
        not target.is_dir()
        or any(
            path.name not in {"air_quality", "air_quality_manifest.json"}
            for path in target.iterdir()
        )
    ):
        raise CurationInputError(
            "Curated OpenAQ directory contains unrelated files; choose a dedicated output root."
        )
    frame = load_processed(input_file)
    table = _table(frame)
    manifest = {
        "schema_version": 1,
        "source_layer": "processed",
        "processed_input_file": input_file.name,
        "row_count": len(frame),
        "counts_by_parameter": {
            name: int(frame["parameter"].eq(name).sum()) for name in ("pm25", "pm10")
        },
        "location_count": int(frame["location_id"].nunique()),
        "sensor_count": int(frame["sensor_id"].nunique()),
        "earliest_measurement_start_utc": frame["datetime_from_utc"].min().isoformat(),
        "latest_measurement_end_utc": frame["datetime_to_utc"].max().isoformat(),
        "partition_columns": PARTITIONS,
        "partition_count": len(frame[PARTITIONS].drop_duplicates()),
        "columns": frame.columns.tolist(),
    }
    output.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".airatlas-curation-stage-", dir=output))
    backup = None
    try:
        _write_dataset(table, stage / "air_quality")
        _validate_written(stage / "air_quality", table)
        (stage / "air_quality_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if target.exists():
            backup = Path(
                tempfile.mkdtemp(prefix=".airatlas-curation-backup-", dir=output)
            )
            target.rename(backup / "openaq")
        try:
            stage.rename(target)
        except OSError:
            if backup is not None:
                (backup / "openaq").rename(target)
                _remove_owned(backup, output)
            raise
        if backup is not None:
            _remove_owned(backup, output)
    finally:
        _remove_owned(stage, output)
        # An unsuccessful first rename may leave only an empty backup container.
        # Keep any backup holding a previous snapshot if rollback itself failed.
        if backup is not None and not (backup / "openaq").exists():
            _remove_owned(backup, output)
    return {
        "processed_rows_read": len(frame),
        "curated_rows_written": len(frame),
        **manifest,
        "output_location": str(target / "air_quality"),
        "manifest_path": str(target / "air_quality_manifest.json"),
    }
