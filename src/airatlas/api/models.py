"""Public response contracts; optional weather is JSON null, timestamps are ISO UTC."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Parameter = Literal["pm25", "pm10"]


class Average(BaseModel):
    parameter: Parameter
    unit: str
    average_value: float
    observation_count: int


class Summary(BaseModel):
    monitored_locations: int
    observation_count: int
    weather_coverage: float | None
    earliest_observation: datetime | None
    latest_observation: datetime | None
    averages: list[Average]


class Location(BaseModel):
    location_id: int
    location_name: str | None
    latitude: float | None
    longitude: float | None


class MapLocation(Location):
    parameters: list[Parameter]


class Observation(BaseModel):
    sensor_id: int
    parameter: Parameter
    unit: str
    value: float
    datetime_from_utc: datetime
    datetime_to_utc: datetime
    has_weather_context: bool
    weather_hour_utc: datetime | None
    temperature_2m_c: float | None
    relative_humidity_2m_pct: float | None
    precipitation_mm: float | None
    wind_speed_10m_kmh: float | None
    weather_source: str | None


class LocationDetail(Location):
    latest: list[Observation]
    recent: list[Observation]


class Daily(BaseModel):
    measurement_date_utc: date
    location_id: int
    location_name: str | None
    parameter: Parameter
    unit: str
    observation_count: int
    average_value: float
    minimum_value: float
    maximum_value: float
    weather_context_count: int
    weather_context_percentage: float


class Weather(BaseModel):
    measurement_date_utc: date
    location_id: int
    location_name: str | None
    parameter: Parameter
    unit: str
    observation_count: int
    average_pollution_value: float
    average_temperature_2m_c: float | None
    average_relative_humidity_2m_pct: float | None
    average_precipitation_mm: float | None
    average_wind_speed_10m_kmh: float | None
    temperature_observation_count: int
    humidity_observation_count: int
    precipitation_observation_count: int
    wind_observation_count: int


class Series[T](BaseModel):
    rows: list[T]
    truncated: bool
    limit: int


class Comparison(BaseModel):
    location_id: int
    location_name: str | None
    parameter: Parameter
    unit: str
    observation_count: int
    average_value: float
    minimum_value: float
    maximum_value: float
    earliest_observation_utc: datetime
    latest_observation_utc: datetime
    weather_context_count: int
    weather_context_percentage: float


class Run(BaseModel):
    run_id: str
    run_mode: str
    requested_start: datetime
    requested_end: datetime
    location_id: int | None
    status: Literal["running", "succeeded", "failed"]
    current_stage: str
    failed_stage: str | None
    started_at: datetime
    finished_at: datetime | None
    observations_loaded: int | None


class DataHealth(BaseModel):
    latest_run: Run | None
    summary: Summary
