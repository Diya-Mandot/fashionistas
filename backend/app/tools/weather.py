"""Adapt the existing SDK tool contract to the standalone weather client."""

from app.integrations.agents_client import AgentTool
from app.integrations.weather import WeatherClient, WeatherRequest


def weather_tool(client: WeatherClient) -> AgentTool:
    async def get_weather(request: WeatherRequest):
        return await client.get_weather_forecast(request)

    return AgentTool(
        name="get_weather_forecast",
        description="Read Open-Meteo forecasts for a city and inclusive date range. Dates use the city's timezone. "
                    "For ambiguous cities, ask the user to select a returned location_id. "
                    "Missing dates and failed lookups are unavailable, not dry weather.",
        input_model=WeatherRequest, handler=get_weather,
    )
