from datetime import date

from app.seed import calendar_events, closet_items


def test_seed_has_no_waterproof_outerwear():
    items = closet_items()
    assert len(items) >= 25
    assert not any(i.waterproof for i in items if i.category == "outerwear")


def test_calendar_is_relative_to_today():
    events = calendar_events(date(2026, 10, 24))  # a Saturday
    names = {e["name"]: e["date"] for e in events}
    assert names["Team Dinner at Canlis"] == "2026-10-27"  # next Tuesday
    assert names["Networking Brunch"] == "2026-10-24"  # this Saturday
    assert all(e["date"] >= "2026-10-24" for e in events)


def test_closet_filters_and_crud(client):
    all_items = client.get("/api/closet").json()
    shoes = client.get("/api/closet", params={"category": "shoes"}).json()
    assert 0 < len(shoes) < len(all_items)
    assert client.get("/api/closet", params={"waterproof": True}).json() == []

    item_id = shoes[0]["id"]
    res = client.patch(f"/api/closet/{item_id}", json={"waterproof": True})
    assert res.json()["waterproof"] is True
    assert client.delete(f"/api/closet/{item_id}").status_code == 204
    assert client.delete(f"/api/closet/{item_id}").status_code == 404
