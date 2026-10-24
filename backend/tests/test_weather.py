import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from agents.strict_schema import ensure_strict_json_schema
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.integrations.weather import WeatherClient, WeatherRequest
from app.main import app
from app.routers.weather import get_weather_client
from app.tools.weather import weather_tool

TODAY = date(2026, 10, 24)
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
SEATTLE = {"id": 5809844, "name": "Seattle", "latitude": 47.6062, "longitude": -122.3321,
           "country_code": "US", "admin1": "Washington", "timezone": "America/Los_Angeles"}


def forecast():
    return {"timezone": "America/Los_Angeles",
            "daily_units": {"time": "iso8601", "temperature_2m_max": "°F", "temperature_2m_min": "°F",
                            "precipitation_probability_max": "%", "weather_code": "wmo code"},
            "daily": {"time": [(TODAY + timedelta(days=i)).isoformat() for i in range(16)],
                      "temperature_2m_max": [58.5] * 16, "temperature_2m_min": [45.0] * 16,
                      "precipitation_probability_max": [80] * 16, "weather_code": [61] * 16}}


def request(**overrides):
    return WeatherRequest(**{"city": "Seattle", "start": TODAY, "end": TODAY + timedelta(days=1), **overrides})


def service(http, **overrides):
    return WeatherClient(Settings(_env_file=None), http, now=lambda: NOW, **overrides)


def test_forecast_queries_units_timezone_and_reuses_cache():
    async def run():
        calls = []

        def respond(req):
            calls.append(req)
            if req.url.host == "geocoding-api.open-meteo.com":
                assert req.url.params["name"] == "Seattle"
                assert req.url.params["countryCode"] == "US"
                return httpx.Response(200, json={"results": [SEATTLE]})
            assert req.url.host == "api.open-meteo.com"
            assert req.url.params["temperature_unit"] == "fahrenheit"
            assert req.url.params["forecast_days"] == "16"
            assert req.url.params["timezone"] == SEATTLE["timezone"]
            assert "precipitation_probability_max" in req.url.params["daily"]
            return httpx.Response(200, json=forecast())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            weather = service(http)
            result = await weather.get_weather_forecast(request(country_code="US"))
            assert result.status == "available" and result.source == "live"
            assert result.location.id == SEATTLE["id"]
            assert result.days[0].high_f == 58.5
            assert result.days[0].precip_pct == 80
            assert result.days[0].summary == "Rain"
            assert result.fetched_at == NOW
            assert result.cached is False
            assert result.missing_dates == []
            again = await weather.get_weather_forecast(request(country_code="US", end=TODAY + timedelta(days=3)))
            assert again.cached is True
            assert len(again.days) == 4
            assert len(calls) == 2
    asyncio.run(run())


def test_ambiguous_city_requires_selection_before_forecast():
    async def run():
        calls = []
        alternate = {**SEATTLE, "id": 9999, "country_code": "CA", "admin1": "British Columbia"}

        def respond(req):
            calls.append(req)
            return httpx.Response(200, json={"results": [SEATTLE, alternate]} if len(calls) == 1 else forecast())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            weather = service(http)
            ambiguous = await weather.get_weather_forecast(request())
            assert ambiguous.status == "ambiguous" and ambiguous.source == "unavailable"
            assert len(ambiguous.location_choices) == 2
            assert all(day.high_f is None for day in ambiguous.days)
            assert len(calls) == 1
            selected = await weather.get_weather_forecast(request(location_id=SEATTLE["id"]))
            assert selected.location.id == SEATTLE["id"]
            assert selected.status == "available"
            assert len(calls) == 2
    asyncio.run(run())


def test_exact_city_match_excludes_nearby_prefixes_and_airports():
    async def run():
        nearby = {**SEATTLE, "id": 7176034, "name": "Seattle Hill", "feature_code": "PPL"}
        airport = {**SEATTLE, "id": 5809876, "name": "Seattle", "feature_code": "AIRP"}
        def respond(req):
            return httpx.Response(200, json={"results": [nearby, airport, SEATTLE]} if "geocoding" in req.url.host else forecast())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            result = await service(http).get_weather_forecast(request(city="Seattle, WA"))
        assert result.status == "available"
        assert result.location.id == SEATTLE["id"]
    asyncio.run(run())


@pytest.mark.parametrize("results", [[], None])
def test_missing_or_invalid_locations(results):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"results": results}))) as http:
            result = await service(http).get_weather_forecast(request())
        assert result.status == ("not_found" if results == [] else "unavailable")
        assert result.source == "unavailable"
        assert result.warnings
    asyncio.run(run())


def test_forecast_horizon_preserves_requested_dates_and_missing_values():
    async def run():
        data = forecast()
        data["daily"]["precipitation_probability_max"][0] = None

        def respond(req):
            return httpx.Response(200, json={"results": [SEATTLE]} if "geocoding" in req.url.host else data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            result = await service(http).get_weather_forecast(request(start=TODAY - timedelta(days=1), end=TODAY + timedelta(days=17)))
        assert result.status == "partial"
        assert len(result.days) == 19
        assert result.days[0].date == TODAY - timedelta(days=1)
        assert result.days[0].status == "unavailable"
        assert result.days[1].status == "partial"
        assert result.days[1].precip_pct is None
        assert result.days[-1].high_f is None
        assert result.days[-1].date == TODAY + timedelta(days=17)
        assert result.missing_dates == [TODAY - timedelta(days=1), TODAY, TODAY + timedelta(days=16), TODAY + timedelta(days=17)]
    asyncio.run(run())


def test_fully_outside_horizon_does_not_call_forecast():
    async def run():
        calls = []

        def respond(req):
            calls.append(req)
            assert "geocoding" in req.url.host
            return httpx.Response(200, json={"results": [SEATTLE]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            result = await service(http).get_weather_forecast(request(start=TODAY + timedelta(days=30), end=TODAY + timedelta(days=31)))
        assert result.status == "unavailable"
        assert len(calls) == 1
        assert len(result.missing_dates) == 2
    asyncio.run(run())


def test_date_boundaries_use_destination_timezone():
    async def run():
        def respond(req):
            return httpx.Response(200, json={"results": [SEATTLE]} if "geocoding" in req.url.host else forecast())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            # Already October 25 UTC, but still October 24 in Seattle.
            weather = WeatherClient(Settings(_env_file=None), http,
                now=lambda: datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc))
            result = await weather.get_weather_forecast(request())
        assert result.status == "available"
        assert result.days[0].date == TODAY
    asyncio.run(run())


def test_cache_expires_after_30_minutes():
    async def run():
        ticks = [0]
        calls = []

        def respond(req):
            calls.append(req)
            return httpx.Response(200, json={"results": [SEATTLE]} if "geocoding" in req.url.host else forecast())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            weather = service(http, clock=lambda: ticks[0])
            await weather.get_weather_forecast(request())
            ticks[0] = 1799
            assert (await weather.get_weather_forecast(request())).cached
            ticks[0] = 1800
            assert not (await weather.get_weather_forecast(request())).cached
        assert len(calls) == 4
    asyncio.run(run())


@pytest.mark.parametrize("invalid", ["units", "timezone", "alignment", "range", "null_daily", "duplicate_dates", "bad_temperature"])
def test_invalid_provider_data_is_unavailable_and_not_reused(invalid):
    async def run():
        data = forecast()
        if invalid == "units":
            data["daily_units"]["temperature_2m_max"] = "°C"
        elif invalid == "timezone":
            data["timezone"] = "UTC"
        elif invalid == "alignment":
            data["daily"]["weather_code"].pop()
        elif invalid == "range":
            data["daily"]["precipitation_probability_max"][0] = 101
        elif invalid == "null_daily":
            data["daily"] = None
        elif invalid == "duplicate_dates":
            data["daily"]["time"][1] = data["daily"]["time"][0]
        else:
            data["daily"]["temperature_2m_max"][0] = 20
        calls = []

        def respond(req):
            calls.append(req)
            return httpx.Response(200, json={"results": [SEATTLE]} if "geocoding" in req.url.host else data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            weather = service(http)
            first = await weather.get_weather_forecast(request())
            second = await weather.get_weather_forecast(request())
        assert first.status == second.status == "unavailable"
        assert all(day.high_f is None for day in first.days)
        assert len(calls) == 4
    asyncio.run(run())


def test_rate_limit_retry_then_success():
    async def run():
        calls = []

        def respond(req):
            calls.append(req)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"results": [SEATTLE]} if "geocoding" in req.url.host else forecast())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            result = await service(http).get_weather_forecast(request())
        assert result.status == "available"
        assert len(calls) == 3
    asyncio.run(run())


def test_network_failure_is_not_dry_weather():
    async def run():
        calls = []

        def respond(req):
            calls.append(req)
            raise httpx.ConnectError("offline", request=req)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            result = await service(http).get_weather_forecast(request())
        assert result.status == "unavailable" and result.source == "unavailable"
        assert result.days[0].precip_pct is None
        assert len(calls) == 2
    asyncio.run(run())


def test_long_retry_after_does_not_retry_early():
    async def run():
        calls = []
        def respond(req):
            calls.append(req)
            return httpx.Response(429, headers={"Retry-After": "60"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            result = await service(http).get_weather_forecast(request())
        assert result.status == "unavailable"
        assert len(calls) == 1
    asyncio.run(run())


def test_total_timeout_is_bounded():
    async def run():
        async def respond(req):
            await asyncio.sleep(1)
            return httpx.Response(200, json={"results": [SEATTLE]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            weather = WeatherClient(Settings(_env_file=None, weather_total_timeout_seconds=0.01), http, now=lambda: NOW)
            result = await weather.get_weather_forecast(request())
        assert result.status == "unavailable"
        assert result.warnings
    asyncio.run(run())


@pytest.mark.parametrize("overrides", [{"end": TODAY - timedelta(days=1)}, {"end": TODAY + timedelta(days=31)},
                                        {"city": "  "}, {"country_code": "USA"}, {"location_id": -1}])
def test_invalid_requests_rejected(overrides):
    with pytest.raises(ValidationError):
        request(**overrides)


def test_weather_route_uses_shared_service_and_validates_dates():
    """TestClient runs async handlers on its own loop; no persistent HTTP connections."""
    class FakeWeather:
        async def get_weather_forecast(self, args):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(
                200, json={"results": [SEATTLE]} if "geocoding" in req.url.host else forecast()))) as http:
                return await service(http).get_weather_forecast(args)

    app.dependency_overrides[get_weather_client] = lambda: FakeWeather()
    try:
        client = TestClient(app)
        response = client.get("/api/weather", params={"city": "Seattle", "start": TODAY.isoformat(), "end": TODAY.isoformat()})
        assert response.status_code == 200
        assert response.json()["days"][0]["high_f"] == 58.5
        invalid = client.get("/api/weather", params={"city": "Seattle", "start": TODAY.isoformat(), "end": "2026-10-01"})
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_weather_tool_uses_existing_agent_contract():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(
            200, json={"results": [SEATTLE]} if "geocoding" in req.url.host else forecast()))) as http:
            tool = weather_tool(service(http))
            schema = ensure_strict_json_schema(tool.input_model.model_json_schema())
            assert schema["additionalProperties"] is False
            assert tool.name == "get_weather_forecast"
            result = await tool.handler(request())
            assert result.status == "available"
    asyncio.run(run())
