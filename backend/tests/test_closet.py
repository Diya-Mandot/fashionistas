from datetime import date

from app.seed import calendar_events, closet_items


def test_seed_has_no_waterproof_outerwear():
    items = closet_items()
    assert len(items) >= 20
    assert all(i.image_url.startswith("/media/seed/photos/") for i in items)
    assert not any(i.waterproof for i in items if i.category == "outerwear")


def test_calendar_is_relative_to_today():
    events = calendar_events(date(2026, 10, 24))  # a Saturday
    names = {e["name"]: e["date"] for e in events}
    assert names["Team Dinner at Canlis"] == "2026-10-27"  # next Tuesday
    assert names["Networking Brunch"] == "2026-10-24"  # this Saturday
    assert all(e["date"] >= "2026-10-24" for e in events)


def test_closet_filters_and_crud(client):
    all_items = client.get("/api/closet").json()
    skirts = client.get("/api/closet", params={"category": "bottoms"}).json()
    assert 0 < len(skirts) < len(all_items)
    assert client.get("/api/closet", params={"waterproof": True}).json() == []

    item_id = skirts[0]["id"]
    res = client.patch(f"/api/closet/{item_id}", json={"waterproof": True})
    assert res.json()["waterproof"] is True
    assert client.delete(f"/api/closet/{item_id}").status_code == 204
    assert client.delete(f"/api/closet/{item_id}").status_code == 404


def test_photo_manifest_builds_closet(tmp_path, monkeypatch):
    import json

    from app import seed

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"id": "itm_photo01", "file": "01-tee.jpg", "name": "Olive Tee", "category": "tops", "formality": "casual",
         "days_since_worn": 3, "times_worn": 24, "is_favorite": True},
        {"file": "02-trench.jpg", "name": "Tan Trench", "category": "outerwear", "waterproof": False},
        {"file": "03-unlabelled.jpg"},
    ]))
    monkeypatch.setattr(seed, "PHOTO_MANIFEST", manifest)
    items = seed.closet_items(date(2026, 10, 24))
    assert [i.id for i in items] == ["itm_photo01", "itm_photo02"]
    tee = items[0]
    assert tee.image_url == "/media/seed/photos/01-tee.jpg"
    assert tee.last_worn == date(2026, 10, 21) and tee.number_of_times_worn == 24 and tee.is_favorite
