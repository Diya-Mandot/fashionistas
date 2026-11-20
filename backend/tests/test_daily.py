from datetime import date

import respx

from app.config import get_settings
from app.routers import daily
from app.services import calendar_source
from app.tools import weather as weather_mod

from tests.test_agent import _mock_open_meteo

DAY = "2026-10-28"
ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
DTSTART:20261028T090000
SUMMARY:Coffee with Sam
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART:20261028T190000
SUMMARY:Client pitch dinner
DESCRIPTION:Dress code: business casual
END:VEVENT
END:VCALENDAR
"""


def _reset():
    daily._cache.clear()
    weather_mod._forecast_cache.clear()
    weather_mod._geo_cache.clear()
    calendar_source._cache.clear()


def _post(client, **body):
    with respx.mock(assert_all_called=False) as router:
        _mock_open_meteo(router, start="2026-10-24")
        return client.post("/api/daily", json={"date": DAY, "city": "Seattle", **body})


def test_main_occasion_picks_dressiest_then_earliest():
    events = [
        {"id": "a", "name": "Gym", "dress_code_hint": "athletic"},
        {"id": "b", "name": "Pitch", "dress_code_hint": "business casual"},
        {"id": "c", "name": "Board", "dress_code_hint": "business casual"},
    ]
    assert daily.main_occasion(events)["id"] == "b"
    assert daily.main_occasion([]) is None


def test_pick_distinct_never_repeats_clothing_and_may_return_fewer():
    from types import SimpleNamespace as NS
    from app.tools.outfits import pick_distinct

    by_id = {"t1": NS(category="tops"), "t2": NS(category="tops"), "b1": NS(category="bottoms"),
             "b2": NS(category="bottoms"), "s1": NS(category="shoes"), "j1": NS(category="outerwear")}
    cands = [["t1", "b1", "s1", "j1"], ["t2", "b1", "s1"], ["t2", "b2", "s1", "j1"], ["t2", "b2", "s1"]]
    got = pick_distinct(cands, lambda c: c, by_id, 5)
    assert got == [["t1", "b1", "s1", "j1"], ["t2", "b2", "s1"]]  # shoes shared only as a last resort


def test_everyday_outfits_are_all_different_and_use_the_weather(client):
    _reset()
    res = _post(client)
    assert res.status_code == 200
    body = res.json()
    assert body["occasion"] is None and body["events"] == []
    assert body["weather"]["high_f"] == 54 and body["weather"]["date"] == DAY
    outfits = body["outfits"]
    assert 2 <= len(outfits) <= daily.N_OUTFITS
    items = {i["id"]: i for i in body["items"]}
    assert all(set(o["item_ids"]) <= set(items) for o in outfits)
    # No piece of clothing appears in two options; only shoes/bags/accessories may repeat.
    seen: dict[str, int] = {}
    for o in outfits:
        for i in o["item_ids"]:
            seen[i] = seen.get(i, 0) + 1
    repeated = [items[i]["category"] for i, n in seen.items() if n > 1]
    assert all(c in ("shoes", "bags", "accessories") for c in repeated), repeated
    titles = [o["title"] for o in outfits]
    assert len(set(titles)) == len(titles) and all(o["tip"] for o in outfits)


def test_occasion_comes_from_calendar_and_can_be_switched(client, tmp_path, monkeypatch):
    _reset()
    f = tmp_path / "cal.ics"
    f.write_text(ICS)
    monkeypatch.setattr(get_settings(), "calendar_ics_url", str(f))

    body = _post(client).json()
    assert [e["name"] for e in body["events"]] == ["Coffee with Sam", "Client pitch dinner"]
    assert body["occasion"]["name"] == "Client pitch dinner"  # business casual beats smart casual

    coffee = body["events"][0]["id"]
    assert _post(client, event_id=coffee).json()["occasion"]["name"] == "Coffee with Sam"
    assert _post(client, event_id="everyday").json()["occasion"] is None


def test_exclude_returns_different_outfits(client):
    _reset()
    first = _post(client).json()["outfits"]
    shown = [o["item_ids"] for o in first]
    second = _post(client, exclude=shown).json()["outfits"]
    assert second
    assert not {frozenset(o["item_ids"]) for o in second} & {frozenset(s) for s in shown}


def test_wear_marks_items_and_repicking_replaces(client):
    _reset()
    outfits = _post(client).json()["outfits"]
    a, b = outfits[0]["item_ids"], outfits[1]["item_ids"]
    before = {i["id"]: i for i in client.get("/api/closet").json()}
    today = date.today().isoformat()

    assert client.post("/api/daily/wear", json={"date": today, "item_ids": a}).status_code == 200
    closet = {i["id"]: i for i in client.get("/api/closet").json()}
    for i in a:
        assert closet[i]["last_worn"] == today
        assert closet[i]["number_of_times_worn"] == before[i]["number_of_times_worn"] + 1

    # Changing your mind the same day undoes the first pick.
    assert client.post("/api/daily/wear", json={"date": today, "item_ids": b}).status_code == 200
    closet = {i["id"]: i for i in client.get("/api/closet").json()}
    for i in set(a) - set(b):
        assert closet[i]["last_worn"] == before[i]["last_worn"]
        assert closet[i]["number_of_times_worn"] == before[i]["number_of_times_worn"]
    for i in b:
        assert closet[i]["number_of_times_worn"] == before[i]["number_of_times_worn"] + 1

    with respx.mock(assert_all_called=False) as router:
        _mock_open_meteo(router, start=today)
        assert client.post("/api/daily", json={"date": today, "city": "Seattle"}).json()["worn_item_ids"] == b


def test_wear_rejects_unknown_items(client):
    res = client.post("/api/daily/wear", json={"item_ids": ["itm_nope"]})
    assert res.status_code == 404
