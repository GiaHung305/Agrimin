"""Validated, prompt-safe contract for external weather tool results."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.security_checks import contains_prompt_injection


LOCAL_WEATHER_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_FORECAST_HORIZON_DAYS = 3


class WeatherContractError(ValueError):
    """Raised when external weather data is unsafe or implausible."""


class ForecastDay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: date
    temp: float | None = Field(default=None, ge=-80, le=65, allow_inf_nan=False)
    temp_min: float | None = Field(default=None, ge=-80, le=65, allow_inf_nan=False)
    temp_max: float | None = Field(default=None, ge=-80, le=65, allow_inf_nan=False)
    humidity: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    humidity_max: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    description: str | None = Field(default=None, max_length=160)
    rain_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    rain_mm: float = Field(ge=0, le=1000, allow_inf_nan=False)

    @field_validator("description")
    @classmethod
    def description_must_be_prompt_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        if contains_prompt_injection(normalized):
            raise ValueError("unsafe weather description")
        return normalized or None

    @model_validator(mode="after")
    def temperature_range_must_be_consistent(self) -> "ForecastDay":
        if (
            self.temp_min is not None
            and self.temp_max is not None
            and self.temp_min > self.temp_max
        ):
            raise ValueError("weather minimum exceeds maximum")
        if self.temp is not None:
            if self.temp_min is not None and self.temp < self.temp_min:
                raise ValueError("weather average is below minimum")
            if self.temp_max is not None and self.temp > self.temp_max:
                raise ValueError("weather average is above maximum")
        if (
            self.humidity is not None
            and self.humidity_max is not None
            and self.humidity > self.humidity_max
        ):
            raise ValueError("weather average humidity exceeds maximum")
        return self


class WeatherResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    forecast: list[ForecastDay] = Field(min_length=1, max_length=3)
    from_cache: bool = False


def local_weather_date() -> date:
    """Return the agricultural operating date, independent of host timezone."""
    return datetime.now(LOCAL_WEATHER_TZ).date()


def _validate_forecast_dates(result: WeatherResult, today: date) -> None:
    dates = [item.date for item in result.forecast]
    if len(dates) != len(set(dates)) or dates != sorted(dates):
        raise WeatherContractError("weather forecast dates are not ordered")
    first_date = dates[0]
    if first_date < today or first_date > today + timedelta(days=1):
        raise WeatherContractError("weather forecast start date is invalid")
    expected_dates = [
        first_date + timedelta(days=offset)
        for offset in range(len(dates))
    ]
    if dates != expected_dates:
        raise WeatherContractError("weather forecast dates are not consecutive")
    if dates[-1] > today + timedelta(days=MAX_FORECAST_HORIZON_DAYS):
        raise WeatherContractError("weather forecast exceeds supported horizon")


def normalize_weather_result(
    payload: object,
    *,
    today: date | None = None,
) -> dict:
    """Return only validated fields that are safe to insert into AI prompts."""
    try:
        result = WeatherResult.model_validate(payload)
        _validate_forecast_dates(result, today or local_weather_date())
    except (TypeError, ValueError) as exc:
        raise WeatherContractError("weather tool returned invalid data") from exc
    return result.model_dump(mode="json")
