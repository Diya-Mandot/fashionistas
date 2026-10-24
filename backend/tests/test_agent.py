from datetime import date

import httpx
import respx

from app.agent.plan import assemble_plan
from app.integrations.agents_client import _parse_city, _parse_dates, _parse_vibe
from app.tools import weather as weather_mod
from app.tools.context import OutfitOption, RunContext
from app.tools.weather import get_weather_forecast

SAT = date(2026, 10, 24)
SEATTLE = "Packing for a tech conference in Seattle Tue–Thu. There's a fancy dinner Tuesday night and I want to look professional but a little edgy."


def _ctx(**kw):
    return RunContext(run_id="t", message="m", today=kw.pop("today", date.today()), home_city="San Francisco", emit=lambda s: None, **kw)


def _mock_open_meteo(router, start="2026-10-24", n=16, precip=70):
    router.get(weather_mod.GEOCODE_URL).mock(
        return_value=httpx.Response(200, json={"results": [{"name": "Seattle", "admin1": "Washington", "latitude": 47.6, "longitude": -122.3}]})
    )
    days = [date.fromordinal(date.fromisoformat(start).toordinal() + i).isoformat() for i in range(n)]
    router.get(weather_mod.FORECAST_URL).mock(
        return_value=httpx.Response(200, json={"daily": {
            "time": days, "temperature_2m_max": [54.2] * n, "temperature_2m_min": [46.1] * n,
            "precipitation_probability_max": [precip] * n, "weather_code": [61] * n,
        }})
    )


def test_message_parsing():
    assert _parse_city(SEATTLE, "San Francisco") == ("Seattle", True)
    assert _parse_city("Pack my bag for NYC this weekend", "SF")[0] == "New York"
    assert _parse_city("First day at a new job Monday", "Boston") == ("Boston", False)
    assert _parse_dates(SEATTLE, SAT) == (date(2026, 10, 27), date(2026, 10, 29))
    assert _parse_dates("NYC this weekend", SAT) == (date(2026, 10, 24), date(2026, 10, 25))
    assert _parse_vibe(SEATTLE) == "professional but a little edgy"


def test_weather_tool_live_and_beyond_window():
    weather_mod._forecast_cache.clear()
    weather_mod._geo_cache.clear()
    with respx.mock(assert_all_called=False) as router:
        _mock_open_meteo(router)
        ctx = _ctx(today=SAT)
        out = get_weather_forecast(ctx, "Seattle", "2026-10-27", "2026-10-29")
        assert out.source == "live"
        assert [d["date"] for d in out.result["days"]] == ["2026-10-27", "2026-10-28", "2026-10-29"]
        assert out.result["days"][0]["high_f"] == 54
        assert "rain likely" in out.title
        far = get_weather_forecast(ctx, "Seattle", "2027-03-01", "2027-03-03")
        assert "beyond" in far.result["note"]
        assert len(far.result["days"]) == 3


def test_weather_tool_falls_back_to_seasonal():
    weather_mod._forecast_cache.clear()
    weather_mod._geo_cache.clear()
    with respx.mock() as router:
        router.get(weather_mod.GEOCODE_URL).mock(side_effect=httpx.ConnectTimeout("boom"))
        out = get_weather_forecast(_ctx(today=SAT), "Seattle", "2026-10-27", "2026-10-28")
    assert out.kind == "fallback" and out.source == "rule"
    assert "seasonal average for Seattle" in out.result["note"]
    assert len(out.result["days"]) == 2


def test_plan_validation_drops_unknown_refs_and_ids(client):
    ctx = _ctx()
    ctx.outfits["E1-A"] = OutfitOption(
        ref="E1-A", event_name="Dinner", event_date="2026-10-27", item_ids=["itm_photo03", "itm_photo08", "itm_ghost"],
        item_names=[], scores=dict(overall=0.8, vibe=0.9, dress_code=0.8, weather=0.7, color=0.8, freshness=0.9), hint="h",
    )
    plan, warnings = assemble_plan(ctx, {
        "trip": {"city": "Seattle", "start": "2026-10-27", "end": "2026-10-27", "summary": "s"},
        "days": [{"date": "2026-10-27", "events": [
            {"name": "Dinner", "outfit_ref": "E1-A", "rationale": "Sleek.", "item_ids": ["itm_fake"]},
            {"name": "Lunch", "outfit_ref": "E9-Z", "rationale": "?"},
        ]}],
        "gaps": [{"need": "waterproof outer layer", "severity": "must-have", "reason": "rain", "suggestion_ref": "S7"}],
    })
    dinner, lunch = plan.days[0].events
    assert dinner.outfit.item_ids == ["itm_photo03", "itm_photo08"]
    assert lunch.outfit is None
    assert any("E9-Z" in w for w in warnings)
    assert any("itm_fake" in w for w in warnings)
    assert any("no longer in the closet" in w for w in warnings)
    assert any("S7" in w for w in warnings)
    assert plan.gaps[0].suggestion is not None  # must-have gaps always get search links
    assert {p.item_id for p in plan.packing_list} == {"itm_photo03", "itm_photo08"}


def test_plan_endpoint_end_to_end_mock(client):
    weather_mod._forecast_cache.clear()
    weather_mod._geo_cache.clear()
    with respx.mock(assert_all_called=False) as router:
        _mock_open_meteo(router, start=date.today().isoformat())
        res = client.post("/api/stylist/plan", json={"message": SEATTLE, "wait": True})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    plan = body["plan"]
    assert plan["trip"]["city"] == "Seattle"
    names = [e["name"] for d in plan["days"] for e in d["events"]]
    assert "Team Dinner at Canlis" in names
    closet_ids = {i["id"] for i in client.get("/api/closet").json()}
    for d in plan["days"]:
        for e in d["events"]:
            assert set(e["outfit"]["item_ids"]) <= closet_ids
            assert 0 <= e["outfit"]["scores"]["overall"] <= 1
    gaps = {g["need"]: g for g in plan["gaps"]}
    assert "waterproof outer layer" in gaps and "shoes" in gaps  # demo closet has neither
    assert gaps["waterproof outer layer"]["suggestion"]["links"][0]["url"].startswith("https://www.depop.com/search/?q=")
    tools = [s["tool"] for s in body["trace"] if s["kind"] in ("tool_call", "decision", "validation")]
    assert tools[:3] == ["get_weather_forecast", "read_calendar", "query_closet"]
    assert "build_and_score_outfits" in tools and tools[-1] == "submit_plan"
    # Replay via GET works
    again = client.get(f"/api/stylist/runs/{body['run_id']}").json()
    assert again["plan"] == plan and again["sources"]["agent"] == "mock"


def test_brunch_is_not_a_workout():
    from app.services.calendar_source import _hint
    from app.text_rules import is_athletic

    assert not is_athletic("Sunday brunch in Austin")
    assert is_athletic("Morning run") and is_athletic("Running club") and is_athletic("gym")
    assert _hint("Networking Brunch", "") == "smart casual"
    assert _hint("Trail run", "") == "athletic"
