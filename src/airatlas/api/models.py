"""Public response contracts; optional weather is JSON null, timestamps are ISO UTC."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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


class AskAirMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=600)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Message content cannot be blank.")
        return value


class AskAirRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    section: Literal["overview", "locations", "trends", "data-health"] | None = None
    history: list[AskAirMessage] = Field(default_factory=list, max_length=6)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Question cannot be blank.")
        return value

    @model_validator(mode="after")
    def conversation_must_stay_bounded(self):
        if sum(len(message.content) for message in self.history) > 3000:
            raise ValueError("Conversation history is too long.")
        return self


class AskAirResponse(BaseModel):
    answer: str
