from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.integrations.weather import WeatherClient, WeatherForecast, WeatherRequest

router = APIRouter(prefix="/api/weather", tags=["weather"])


@lru_cache
def get_weather_client() -> WeatherClient:
    return WeatherClient()


@router.get("", response_model=WeatherForecast)
async def get_weather(
    city: Annotated[str, Query(min_length=2, max_length=120)], start: date, end: date,
    country_code: Annotated[str | None, Query(pattern="^[A-Z]{2}$")] = None,
    location_id: Annotated[int | None, Query(gt=0)] = None,
    client: WeatherClient = Depends(get_weather_client),
) -> WeatherForecast:
    try:
        request = WeatherRequest(city=city, start=start, end=end, country_code=country_code, location_id=location_id)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Supply a city and an inclusive date range of at most 31 days.") from None
    return await client.get_weather_forecast(request)
