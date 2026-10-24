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


def test_photo_manifest_replaces_and_adds(tmp_path, monkeypatch):
    import json

    from app import seed

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"file": "moto.jpg", "replaces": "itm_seed14"},
        {"file": "trench.jpg", "replaces": None, "name": "Tan Trench", "category": "outerwear",
         "formality": "smart casual", "waterproof": False, "color": "tan"},
    ]))
    monkeypatch.setattr(seed, "PHOTO_MANIFEST", manifest)
    items = {i.id: i for i in seed.closet_items()}
    assert items["itm_seed14"].image_url == "/media/seed/photos/moto.jpg"
    assert items["itm_seed14"].name == "Black Leather Moto Jacket"
    extra = [i for i in items.values() if i.id.startswith("itm_photo")]
    assert len(extra) == 1 and extra[0].name == "Tan Trench" and extra[0].category == "outerwear"
