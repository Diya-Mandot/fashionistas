"""get_weather_forecast: real data from Open-Meteo (free, no key), cached 30 min.

Never fails: beyond the forecast window it returns the furthest available days
with a note; on timeout/error it falls back to a seasonal average and says so.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Optional

import httpx

from app.tools.context import RunContext, ToolOutput

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 6.0
CACHE_TTL_S = 30 * 60
FORECAST_DAYS = 16

_ALIASES = {"nyc": "New York", "new york city": "New York", "sf": "San Francisco", "la": "Los Angeles", "dc": "Washington"}
_geo_cache: dict[str, dict[str, Any]] = {}
_forecast_cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}

_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "showers", 81: "showers", 82: "heavy showers",
    95: "thunderstorms", 96: "thunderstorms", 99: "thunderstorms",
}

# (high_f, low_f, precip_pct) by month, used only when the live API fails.
_SEASONAL = {
    "seattle": [(48, 37, 75), (51, 37, 70), (55, 39, 70), (60, 42, 60), (66, 47, 50), (71, 52, 40), (77, 56, 20), (77, 56, 20), (71, 52, 35), (60, 46, 60), (52, 40, 75), (47, 36, 80)],
    "new york": [(39, 27, 40), (42, 29, 40), (50, 35, 45), (62, 45, 45), (72, 54, 45), (80, 64, 40), (85, 69, 40), (84, 68, 40), (76, 61, 35), (65, 50, 35), (54, 41, 40), (44, 32, 40)],
    "san francisco": [(57, 46, 50), (60, 48, 50), (62, 49, 40), (64, 50, 25), (66, 52, 15), (69, 54, 5), (69, 55, 5), (70, 56, 5), (72, 56, 10), (70, 54, 20), (63, 50, 40), (57, 46, 50)],
}
_GENERIC = [(42, 28, 40), (45, 30, 40), (54, 37, 40), (64, 46, 40), (73, 55, 40), (81, 64, 35), (85, 68, 35), (83, 67, 35), (77, 60, 30), (66, 49, 30), (55, 39, 35), (45, 31, 40)]


def _geocode(city: str) -> dict[str, Any]:
    name = _ALIASES.get(city.strip().lower(), city.strip())
    key = name.lower()
    if key in _geo_cache:
        return _geo_cache[key]
    res = httpx.get(GEOCODE_URL, params={"name": name, "count": 1, "language": "en", "format": "json"}, timeout=TIMEOUT_S)
    res.raise_for_status()
    results = res.json().get("results") or []
    if not results:
        raise LookupError(f"Couldn't find a place called {city!r}")
    _geo_cache[key] = results[0]
    return results[0]


def _forecast(lat: float, lon: float) -> tuple[dict[str, Any], bool]:
    key = (round(lat, 2), round(lon, 2))
    hit = _forecast_cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1], True
    res = httpx.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
        },
        timeout=TIMEOUT_S,
    )
    res.raise_for_status()
    daily = res.json()["daily"]
    _forecast_cache[key] = (time.time(), daily)
    return daily, False


def _parse_date(s: Optional[str], default: date) -> date:
    try:
        return date.fromisoformat(s) if s else default
    except ValueError:
        return default


def _seasonal(city: str, start: date, end: date) -> list[dict[str, Any]]:
    table = _SEASONAL.get(_ALIASES.get(city.lower(), city).lower(), _GENERIC)
    days = []
    d = start
    while d <= end and len(days) < 10:
        hi, lo, pp = table[d.month - 1]
        days.append({"date": d.isoformat(), "high_f": hi, "low_f": lo, "precip_pct": pp, "summary": "seasonal average"})
        d += timedelta(days=1)
    return days


def get_weather_forecast(ctx: RunContext, city: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> ToolOutput:
    start = _parse_date(start_date, ctx.today)
    end = _parse_date(end_date, start + timedelta(days=2))
    if end < start:
        start, end = end, start
    ctx.city = ctx.city or city
    note = None
    try:
        if ctx.home_coords and city.strip().lower() == ctx.home_city.strip().lower():
            place = {"name": ctx.home_city, "latitude": ctx.home_coords[0], "longitude": ctx.home_coords[1], "admin1": None}
        else:
            place = _geocode(city)
        daily, cached = _forecast(place["latitude"], place["longitude"])
        all_days = [
            {
                "date": daily["time"][i],
                "high_f": round(daily["temperature_2m_max"][i]) if daily["temperature_2m_max"][i] is not None else None,
                "low_f": round(daily["temperature_2m_min"][i]) if daily["temperature_2m_min"][i] is not None else None,
                "precip_pct": daily["precipitation_probability_max"][i],
                "summary": _WMO.get(daily["weather_code"][i], "mixed"),
            }
            for i in range(len(daily["time"]))
        ]
        days = [d for d in all_days if start.isoformat() <= d["date"] <= end.isoformat()]
        if not days:
            days = all_days[-3:]
            note = f"Requested dates are beyond the {FORECAST_DAYS}-day forecast; showing the furthest available days."
        label = f"{place['name']}{', ' + place['admin1'] if place.get('admin1') else ''}"
        source, kind = "live", "tool_call"
        detail = ("Cached forecast (≤30 min old) · " if cached else "") + "Open-Meteo"
    except Exception as exc:  # timeout, HTTP error, unknown city
        days = _seasonal(city, start, end)
        label = city
        note = f"Weather API failed ({type(exc).__name__}); used the seasonal average for {city}."
        source, kind, detail = "rule", "fallback", note

    for d in days:
        ctx.weather_by_date[d["date"]] = d
    span = _span_label(days)
    rainy = [d for d in days if (d.get("precip_pct") or 0) >= 50]
    title = f"Checked weather for {label}, {span}"
    if rainy:
        title += f" · rain likely {_span_label(rainy)}"
    result: dict[str, Any] = {"city": label, "days": days}
    if note:
        result["note"] = note
    return ToolOutput(result=result, title=title, detail=note or detail, source=source, kind=kind)


def _span_label(days: list[dict[str, Any]]) -> str:
    if not days:
        return "no days"
    a, b = date.fromisoformat(days[0]["date"]), date.fromisoformat(days[-1]["date"])
    if a == b:
        return a.strftime("%a %b %-d")
    if a.month == b.month:
        return f"{a.strftime('%b %-d')}–{b.strftime('%-d')}"
    return f"{a.strftime('%b %-d')}–{b.strftime('%b %-d')}"
