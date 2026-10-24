"""Open-Meteo forecasts with explicit location and missing-data handling.

Dates refer to the selected city's timezone. Cache entries stay in memory only.
Never substitute other dates, seasonal averages, or synthetic weather.
"""

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from typing import Callable, Literal
from unicodedata import combining, normalize
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.config import Settings, get_settings

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_FIELDS = ("temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "weather_code")


class WeatherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    city: str = Field(min_length=2, max_length=120)
    start: date
    end: date
    country_code: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    location_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_range(self):
        if not 0 <= (self.end - self.start).days <= 30:
            raise ValueError("End must follow start. Request at most 31 days.")
        return self


class Location(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: int = Field(gt=0)
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    country_code: str
    admin1: str | None = None
    timezone: str

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str):
        ZoneInfo(value)
        return value


class WeatherDay(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    date: date
    status: Literal["available", "partial", "unavailable"]
    high_f: float | None = None
    low_f: float | None = None
    precip_pct: float | None = Field(default=None, ge=0, le=100)
    weather_code: int | None = None
    summary: str | None = None


class WeatherForecast(BaseModel):
    status: Literal["available", "partial", "unavailable", "ambiguous", "not_found"]
    source: Literal["live", "unavailable"]
    provider: str = "Open-Meteo"
    attribution_url: str = "https://open-meteo.com/"
    location: Location | None = None
    location_choices: list[Location] = Field(default_factory=list)
    days: list[WeatherDay]
    missing_dates: list[date]
    cached: bool = False
    fetched_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class _Daily(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    time: list[date]
    temperature_2m_max: list[float | None]
    temperature_2m_min: list[float | None]
    precipitation_probability_max: list[float | None]
    weather_code: list[int | None]

    @model_validator(mode="after")
    def valid_columns(self):
        if len(set(self.time)) != len(self.time) or any(len(getattr(self, field)) != len(self.time) for field in DAILY_FIELDS):
            raise ValueError("Daily forecast arrays must align by unique date.")
        for high, low in zip(self.temperature_2m_max, self.temperature_2m_min):
            if high is not None and low is not None and high < low:
                raise ValueError("Forecast high cannot be lower than low.")
        return self


class _ProviderError(RuntimeError):
    pass


def _city_key(name: str) -> str:
    return "".join(char for char in normalize("NFKD", name.casefold()) if not combining(char)).strip()


def _summary(code: int | None) -> str | None:
    if code == 0:
        return "Clear sky"
    if code in (1, 2, 3):
        return "Cloudy"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (95, 96, 99):
        return "Thunderstorms"
    return None


class WeatherClient:
    def __init__(
        self, settings: Settings | None = None, client: httpx.AsyncClient | None = None,
        *, clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.settings = settings or get_settings()
        self.client = client
        self.clock = clock
        self.now = now
        self._cache: OrderedDict[tuple, tuple[float, dict, datetime]] = OrderedDict()

    @asynccontextmanager
    async def _http(self):
        if self.client is not None:
            yield self.client
        else:
            async with httpx.AsyncClient(timeout=self.settings.weather_timeout_seconds) as client:
                yield client

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict, key: tuple):
        entry = self._cache.get(key)
        if entry is not None and self.clock() - entry[0] < self.settings.weather_cache_seconds:
            self._cache.move_to_end(key)
            return entry[1], entry[2], True
        for attempt in range(2):
            try:
                response = await client.get(url, params=params, timeout=self.settings.weather_timeout_seconds)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or data.get("error"):
                    raise _ProviderError("Weather provider returned invalid data.")
                fetched_at = self.now()
                # Responses are validated by the caller. Remove invalid cache entries on failure.
                self._cache[key] = (self.clock(), data, fetched_at)
                self._cache.move_to_end(key)
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
                return data, fetched_at, False
            except (httpx.HTTPError, ValueError) as exc:
                retryable = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError) and (exc.response.status_code == 429 or exc.response.status_code >= 500))
                if not retryable or attempt == 1:
                    raise _ProviderError("Weather provider is unavailable.") from exc
                delay = 0.25
                if isinstance(exc, httpx.HTTPStatusError):
                    try:
                        delay = max(0, float(exc.response.headers.get("Retry-After", delay)))
                    except ValueError:
                        pass
                if delay > 2:
                    # Return unavailable rather than retry before the provider permits it.
                    raise _ProviderError("Weather provider requested a longer retry delay.") from exc
                await asyncio.sleep(delay)

    async def get_weather_forecast(self, request: WeatherRequest) -> WeatherForecast:
        dates = [request.start + timedelta(days=i) for i in range((request.end - request.start).days + 1)]
        empty_days = [WeatherDay(date=day, status="unavailable") for day in dates]
        location = None
        try:
            async with asyncio.timeout(self.settings.weather_total_timeout_seconds), self._http() as client:
                geo_key = ("geocode", request.city.casefold(), request.country_code)
                params = {"name": request.city, "count": 10, "language": "en", "format": "json"}
                if request.country_code:
                    params["countryCode"] = request.country_code
                raw, _, _ = await self._get(client, GEOCODING_URL, params, geo_key)
                results = raw.get("results", [])
                if not isinstance(results, list) or any(not isinstance(result, dict) for result in results):
                    raise _ProviderError("Weather provider returned invalid locations.")
                choices = [Location.model_validate(result) for result in results
                           if isinstance(result, dict) and str(result.get("feature_code", "PPL")).startswith("PPL")]
                if request.country_code:
                    choices = [choice for choice in choices if choice.country_code == request.country_code]
                if request.location_id is not None:
                    choices = [choice for choice in choices if choice.id == request.location_id]
                else:
                    # Search is prefix-based. Seattle Heights must not make Seattle ambiguous.
                    exact = [choice for choice in choices if _city_key(choice.name) == _city_key(request.city.split(",", 1)[0])]
                    choices = exact or choices
                if not choices:
                    return WeatherForecast(status="not_found", source="unavailable", days=empty_days, missing_dates=dates,
                        warnings=["No matching city was found. Supply a city and region or country."])
                if len(choices) > 1:
                    return WeatherForecast(status="ambiguous", source="unavailable", location_choices=choices,
                        days=empty_days, missing_dates=dates, warnings=["Choose a location_id or supply a more specific city before requesting weather."])
                location = choices[0]
                local_today = self.now().astimezone(ZoneInfo(location.timezone)).date()
                horizon_end = local_today + timedelta(days=15)
                if request.end < local_today or request.start > horizon_end:
                    return WeatherForecast(status="unavailable", source="unavailable", location=location,
                        days=empty_days, missing_dates=dates, warnings=["Requested dates fall outside the current forecast window."])
                # A local date in the key prevents yesterday's cached forecast crossing midnight.
                forecast_key = ("forecast", location.latitude, location.longitude, location.timezone, local_today)
                raw, timestamp, cached = await self._get(client, FORECAST_URL, {
                    "latitude": location.latitude, "longitude": location.longitude,
                    "timezone": location.timezone, "temperature_unit": "fahrenheit",
                    "forecast_days": 16, "daily": ",".join(DAILY_FIELDS),
                }, forecast_key)
                units = raw.get("daily_units", {})
                if not isinstance(units, dict) or raw.get("timezone") != location.timezone or units.get("temperature_2m_max") != "°F" or units.get("temperature_2m_min") != "°F" or units.get("precipitation_probability_max") != "%":
                    raise _ProviderError("Weather provider returned unexpected units or timezone.")
                daily = _Daily.model_validate(raw.get("daily"))
                forecast = {}
                for i, day in enumerate(daily.time):
                    high, low = daily.temperature_2m_max[i], daily.temperature_2m_min[i]
                    precip = daily.precipitation_probability_max[i]
                    values = (high, low, precip)
                    status = "available" if all(v is not None for v in values) else "partial" if any(v is not None for v in values) else "unavailable"
                    forecast[day] = WeatherDay(date=day, status=status, high_f=high, low_f=low,
                        precip_pct=precip, weather_code=daily.weather_code[i], summary=_summary(daily.weather_code[i]))
                days = [forecast.get(day, WeatherDay(date=day, status="unavailable"))
                        if local_today <= day <= horizon_end else WeatherDay(date=day, status="unavailable") for day in dates]
                missing = [day.date for day in days if day.status != "available"]
                has_evidence = any(day.status != "unavailable" for day in days)
                return WeatherForecast(status="available" if not missing else "partial" if has_evidence else "unavailable",
                    source="live" if has_evidence else "unavailable", location=location, days=days, missing_dates=missing,
                    fetched_at=timestamp, cached=cached,
                    warnings=["Some requested dates or weather fields are unavailable. Do not substitute other dates."] if missing else [])
        except (_ProviderError, ValidationError, ZoneInfoNotFoundError, TimeoutError):
            # Invalid responses and interrupted requests must not become cached evidence.
            self._cache.clear()
            return WeatherForecast(status="unavailable", source="unavailable", location=location,
                days=empty_days, missing_dates=dates, warnings=["Weather lookup failed or returned invalid data. No forecast was assumed."])
