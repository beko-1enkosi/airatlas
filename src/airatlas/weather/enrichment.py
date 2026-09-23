"""Location/hour enrichment of M3 Parquet; raw and original curated inputs stay intact."""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

from airatlas.curation.parquet import (
    ORDER,
    PARTITIONS,
    REQUIRED,
    _remove_owned,
    _validate_written,
    _write_dataset,
)
from airatlas.processing.normalize import KEY
from airatlas.weather.client import (
    VARIABLES,
    WeatherError,
    coordinates,
    validate_response,
)
from airatlas.weather.storage import get_cached_weather

METRICS = [
    "temperature_2m_c",
    "relative_humidity_2m_pct",
    "precipitation_mm",
    "wind_speed_10m_kmh",
]
WEATHER_COLUMNS = [
    "weather_hour_utc",
    *METRICS,
    "weather_source",
    "weather_latitude",
    "weather_longitude",
]


class MissingLocationCoordinatesError(WeatherError):
    """No trustworthy coordinate pair is available for a represented location."""


def resolve_coordinates(observations, locations):
    """Prefer complete curated pairs; tolerate only <=1e-5 degree variation.

    The tolerance accommodates rounding (~1 m). Choose the smallest pair
    deterministically, never combine partial pairs or average conflicting sites.
    Config supports latitude/longitude fields or a coordinates object.
    """
    configured = {location["id"]: location for location in locations}
    resolved = {}
    for identifier, group in observations.groupby("location_id", sort=True):
        identifier = int(identifier)
        pairs = []
        if {"latitude", "longitude"} <= set(group.columns):
            for lat, lon in group[["latitude", "longitude"]].itertuples(
                index=False, name=None
            ):
                if pd.notna(lat) and pd.notna(lon):
                    pairs.append(coordinates(lat, lon))
        if pairs:
            if any(
                max(pair[index] for pair in pairs) - min(pair[index] for pair in pairs)
                > 1e-5
                for index in (0, 1)
            ):
                raise WeatherError(
                    f"Conflicting curated coordinates for location {identifier}."
                )
            resolved[identifier] = min(pairs)
            continue
        location = configured.get(identifier, {})
        pair = location.get("coordinates") or location
        if (
            not isinstance(pair, dict)
            or pair.get("latitude") is None
            or pair.get("longitude") is None
        ):
            raise MissingLocationCoordinatesError(
                f"No confirmed coordinates for location {identifier}; supply curated coordinates or confirmed MVP configuration coordinates."
            )
        resolved[identifier] = coordinates(pair["latitude"], pair["longitude"])
    return resolved


def normalize_weather(envelope):
    request, response = envelope["request"], envelope["response"]
    times = validate_response(response, request["start_date"], request["end_date"])
    frame = pd.DataFrame(
        {
            "location_id": pd.array(
                [request["location_id"]] * len(times), dtype="Int64"
            ),
            "weather_time_utc": pd.to_datetime(times, utc=True).as_unit("ns"),
        }
    )
    for source, column in zip(VARIABLES, METRICS, strict=True):
        frame[column] = pd.array(response["hourly"][source], dtype="Float64")
    frame["weather_source"] = "open_meteo"
    frame["weather_latitude"] = request["latitude"]
    frame["weather_longitude"] = request["longitude"]
    return frame


def _load_air_quality(input_dir):
    partitioning = ds.partitioning(
        pa.schema([(name, pa.string()) for name in PARTITIONS]), flavor="hive"
    )
    try:
        table = ds.dataset(
            input_dir, format="parquet", partitioning=partitioning
        ).to_table()
    except (OSError, ValueError) as exc:
        raise WeatherError("Cannot read curated air-quality Parquet input.") from exc
    if not REQUIRED.union(PARTITIONS) <= set(table.column_names):
        raise WeatherError("Curated air-quality input is missing required columns.")
    if set(WEATHER_COLUMNS).intersection(table.column_names):
        raise WeatherError("Input already contains weather enrichment columns.")
    if table.num_rows == 0:
        raise WeatherError("Curated air-quality input contains no observations.")
    for column in ("datetime_from_utc", "datetime_to_utc"):
        dtype = table.schema.field(column).type
        if not pa.types.is_timestamp(dtype) or dtype.tz != "UTC":
            raise WeatherError("Curated periods must be typed UTC timestamps.")
    for column in ("location_id", "sensor_id"):
        if (
            not pa.types.is_integer(table.schema.field(column).type)
            or table[column].null_count
        ):
            raise WeatherError(
                "Curated location and sensor IDs must be non-null integers."
            )
    frame = table.to_pandas()
    if (
        not frame["source"].eq("openaq").all()
        or not frame["parameter"].isin(["pm25", "pm10"]).all()
    ):
        raise WeatherError("Expected OpenAQ PM2.5/PM10 observations.")
    if (
        frame[KEY].isna().any().any()
        or (frame[["location_id", "sensor_id"]] <= 0).any().any()
        or not (frame["datetime_to_utc"] > frame["datetime_from_utc"]).all()
    ):
        raise WeatherError("Invalid curated observation identity or period.")
    if frame.duplicated(KEY).any():
        raise WeatherError("Duplicate air-quality observation keys in input.")
    if (
        not frame["measurement_date_utc"]
        .eq(frame["datetime_to_utc"].dt.strftime("%Y-%m-%d"))
        .all()
    ):
        raise WeatherError(
            "Curated partition dates disagree with measurement period end."
        )
    return table, frame.sort_values(ORDER, kind="stable").reset_index(drop=True)


def _publish(table, manifest, output):
    """Stage and validate before swapping the owned enriched namespace.

    Single writer, same limitations as M3: rollback on ordinary rename failure;
    retain a backup if rollback fails. Not a power-loss/concurrent-reader transaction.
    """
    output.mkdir(parents=True, exist_ok=True)
    target = output / "open_meteo_air_quality"
    stage = Path(tempfile.mkdtemp(prefix=".airatlas-curation-weather-", dir=output))
    backup = None
    try:
        _write_dataset(table, stage / "air_quality_weather")
        _validate_written(stage / "air_quality_weather", table)
        (stage / "air_quality_weather_manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        if target.exists():
            backup = Path(
                tempfile.mkdtemp(prefix=".airatlas-curation-backup-", dir=output)
            )
            target.rename(backup / "previous")
        try:
            stage.rename(target)
        except OSError:
            if backup is not None:
                (backup / "previous").rename(target)
            raise
        if backup is not None:
            _remove_owned(backup, output)
    finally:
        _remove_owned(stage, output)
        if backup is not None and not (backup / "previous").exists():
            _remove_owned(backup, output)
    return target


def enrich_air_quality_weather(
    client, input_dir, raw_weather_dir, output_dir, *, locations=None
):
    """Cache historical UTC hours, then left-join by location and period-end hour.

    Match counts require an hourly record with at least one non-null variable.
    An all-null hour is unavailable; partial weather keeps its remaining nulls.
    Raw cache writes are immutable per request and can survive a failed rebuild.
    """
    input_dir, raw_root, output = (
        Path(input_dir).resolve(),
        Path(raw_weather_dir).resolve(),
        Path(output_dir).resolve(),
    )
    target = output / "open_meteo_air_quality"
    repository = Path(__file__).resolve().parents[3]
    protected = [
        input_dir,
        raw_root,
        repository / "data/raw",
        repository / "data/processed",
    ]
    if (
        any(
            target.is_relative_to(path) or path.is_relative_to(target)
            for path in protected
        )
        or raw_root.is_relative_to(input_dir)
        or input_dir.is_relative_to(raw_root)
    ):
        raise WeatherError(
            "Weather output, raw cache, and curated input must not overlap."
        )
    if target.resolve() != target or target.is_symlink():
        raise WeatherError("Enriched output must not be a symlink or junction.")
    if target.exists() and (
        not target.is_dir()
        or any(
            path.name
            not in {"air_quality_weather", "air_quality_weather_manifest.json"}
            for path in target.iterdir()
        )
    ):
        raise WeatherError("Enriched output namespace contains unrelated files.")
    table, observations = _load_air_quality(input_dir)
    if locations is None:
        locations = json.loads(
            (repository / "config/mvp_locations.json").read_text(encoding="utf-8")
        )["locations"]
    pairs = resolve_coordinates(observations, locations)
    # Resolve every location before any HTTP request or raw write.
    weather, hits = [], 0
    requests_before = client.requests_made
    for identifier, group in observations.groupby("location_id", sort=True):
        latitude, longitude = pairs[int(identifier)]
        names = sorted(group["location_name"].dropna().unique())
        envelope, hit = get_cached_weather(
            client,
            raw_root,
            location_id=int(identifier),
            location_name=names[0] if names else None,
            latitude=latitude,
            longitude=longitude,
            start_date=group["datetime_to_utc"].min().date().isoformat(),
            end_date=group["datetime_to_utc"].max().date().isoformat(),
        )
        weather.append(normalize_weather(envelope))
        hits += int(hit)
    hours = pd.concat(weather, ignore_index=True)
    available = hours.loc[hours[METRICS].notna().any(axis=1)].rename(
        columns={"weather_time_utc": "weather_hour_utc"}
    )
    if available.duplicated(["location_id", "weather_hour_utc"]).any():
        raise WeatherError("Duplicate location/hour weather keys.")
    observations["weather_hour_utc"] = observations["datetime_to_utc"].dt.floor("h")
    enriched = observations.merge(
        available,
        on=["location_id", "weather_hour_utc"],
        how="left",
        validate="many_to_one",
        sort=False,
    )
    enriched = enriched.sort_values(ORDER, kind="stable").reset_index(drop=True)
    if len(enriched) != table.num_rows or enriched.duplicated(KEY).any():
        raise WeatherError(
            "Enrichment changed the air-quality observation count or keys."
        )
    fields = list(table.schema) + [
        pa.field("weather_hour_utc", pa.timestamp("ns", tz="UTC"))
    ]
    fields += [pa.field(column, pa.float64()) for column in METRICS]
    fields += [
        pa.field("weather_source", pa.string()),
        pa.field("weather_latitude", pa.float64()),
        pa.field("weather_longitude", pa.float64()),
    ]
    result = pa.Table.from_pandas(
        enriched, schema=pa.schema(fields), preserve_index=False
    ).replace_schema_metadata(None)
    matched = int(enriched["weather_source"].notna().sum())
    manifest = {
        "schema_version": 1,
        "air_quality_input": input_dir.name,
        "weather_source": "open_meteo",
        "air_quality_rows": len(enriched),
        "weather_rows_available": len(available),
        "weather_matched_rows": matched,
        "weather_unmatched_rows": len(enriched) - matched,
        "weather_match_percentage": 100.0 * matched / len(enriched),
        "location_count": len(pairs),
        "sensor_count": int(enriched["sensor_id"].nunique()),
        "pm25_rows": int(enriched["parameter"].eq("pm25").sum()),
        "pm10_rows": int(enriched["parameter"].eq("pm10").sum()),
        "earliest_measurement": enriched["datetime_from_utc"].min().isoformat(),
        "latest_measurement": enriched["datetime_to_utc"].max().isoformat(),
        "weather_variables": VARIABLES,
        "partition_columns": PARTITIONS,
        "columns": result.column_names,
    }
    destination = _publish(result, manifest, output)
    return {
        **manifest,
        "weather_api_requests": client.requests_made - requests_before,
        "weather_cache_hits": hits,
        "enriched_rows_written": len(enriched),
        "output_location": str(destination / "air_quality_weather"),
    }
