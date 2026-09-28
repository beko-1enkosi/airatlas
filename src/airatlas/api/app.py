"""Local read-only API. Run: uvicorn airatlas.api.app:app --reload."""

import os
import re
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BeforeValidator

from airatlas.api import models, queries
from airatlas.api.database import DatabaseUnavailable, query


def iso_date(value):
    if isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Use an ISO date in YYYY-MM-DD format.")
    return value


ISODate = Annotated[date, BeforeValidator(iso_date)]

app = FastAPI(title="AirAtlas API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("AIRATLAS_FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_methods=["GET"],
    allow_headers=["Accept"],
    allow_credentials=False,
)


@app.exception_handler(DatabaseUnavailable)
@app.exception_handler(ResponseValidationError)
def unavailable(request, exception):
    return JSONResponse(
        status_code=503,
        content={"detail": "Data service unavailable. Try again shortly."},
    )


@app.exception_handler(RequestValidationError)
def invalid_request(request, exception):
    # Do not echo arbitrary request input in error payloads.
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Invalid filter. Use pm25 or pm10, positive location IDs and ISO dates."
        },
    )


@app.get("/api/health")
def health():
    query("SELECT 1 AS connected")
    return {"service": "AirAtlas", "status": "ok", "database": "connected"}


@app.get("/api/summary", response_model=models.Summary)
def summary():
    return queries.summary()


@app.get("/api/locations", response_model=list[models.MapLocation])
def locations():
    return queries.locations()


@app.get("/api/locations/{location_id}", response_model=models.LocationDetail)
def location(location_id: Annotated[int, Path(gt=0, le=2**63 - 1)]):
    result = queries.location_detail(location_id)
    if result is None:
        raise HTTPException(404, "Location not found.")
    return result


def filters(
    parameter: models.Parameter = "pm25",
    location_id: Annotated[int | None, Query(gt=0, le=2**63 - 1)] = None,
    date_from: ISODate | None = None,
    date_to: ISODate | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 1000,
):
    """Dates filter UTC period-end dates inclusively; defaults cover latest 90 days."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Start date must be on or before end date.")
    return parameter, location_id, date_from, date_to, limit


@app.get("/api/trends", response_model=models.Series[models.Daily])
def trends(values: Annotated[tuple, Depends(filters)]):
    return queries.series("trends", *values)


@app.get("/api/comparison/locations", response_model=list[models.Comparison])
def comparison(parameter: models.Parameter = "pm25"):
    return queries.comparison(parameter)


@app.get("/api/weather-context", response_model=models.Series[models.Weather])
def weather(values: Annotated[tuple, Depends(filters)]):
    return queries.series("weather", *values)


@app.get("/api/data-health", response_model=models.DataHealth)
def data_health():
    return queries.data_health()
