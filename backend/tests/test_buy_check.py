"""Should I Buy This? API, in mock mode (no Vision, no Claude)."""

from io import BytesIO

import pytest
from PIL import Image

from app.integrations import decisions_client as dc


def _jpeg(color=(20, 20, 20)) -> bytes:
    im = Image.new("RGB", (400, 500), (235, 232, 225))
    im.paste(color, (100, 100, 300, 400))
    buf = BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def _check(client, name="black_leather_jacket.jpg"):
    return client.post("/api/buy-check", files={"file": (name, _jpeg(), "image/jpeg")})


def test_response_shape(client):
    res = _check(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["check_id"].startswith("chk_")
    item = body["item"]
    assert (item["category"], item["color"], item["subcategory"]) == ("outerwear", "black", "jacket")
    assert item["image_url"].startswith("/media/uploads/pending/")
    assert "scan_meta" not in item
    r = body["result"]
    assert set(r) == {"score", "verdict", "outfit_count", "duplicates", "gap_filled", "calendar_matches",
                      "est_wears_per_year", "top_outfits", "score_reason"}
    assert 0 <= r["score"] <= 100 and r["verdict"] in ("great_buy", "maybe", "skip")
    assert r["outfit_count"] > 0 and 1 <= len(r["top_outfits"]) <= 3
    for outfit in r["top_outfits"]:
        assert outfit["includes_new"] is True
        assert "new" in [i["id"] for i in outfit["items"]]
    assert r["score_reason"]
    kinds = [s["kind"] for s in body["trace"]]
    assert kinds == ["validation", "fallback", "decision", "tool_call", "decision", "final"]
    assert body["trace"][4]["tool"] == "judge_purchase" and body["trace"][4]["source"] == "mock"
    assert body["usage"] == {"checks_used": 1, "limit": 3, "pro": False}
    assert client.get(item["image_url"]).status_code == 200


def test_nothing_saved_until_keep(client):
    before = len(client.get("/api/closet").json())
    check_id = _check(client).json()["check_id"]
    assert len(client.get("/api/closet").json()) == before

    res = client.post(f"/api/buy-check/{check_id}/keep")
    assert res.status_code == 200
    item = res.json()["item"]
    assert item["source"] == "buy_check" and item["category"] == "outerwear"
    assert item["image_url"].startswith("/media/uploads/itm_")
    assert client.get(item["image_url"]).status_code == 200
    closet = client.get("/api/closet").json()
    assert len(closet) == before + 1 and any(i["id"] == item["id"] for i in closet)
    assert client.post(f"/api/buy-check/{check_id}/keep").status_code == 409
    # Refetching the check now points at the moved photo, not the pending one.
    again = client.get(f"/api/buy-check/{check_id}").json()
    assert again["item"]["image_url"] == item["image_url"]
    news = [i for o in again["result"]["top_outfits"] for i in o["items"] if i["id"] == "new"]
    assert news and all(i["image_url"] == item["image_url"] for i in news)


def test_owning_one_makes_the_next_a_duplicate(client):
    first = _check(client).json()
    client.post(f"/api/buy-check/{first['check_id']}/keep")
    second = _check(client).json()["result"]
    assert [d["name"] for d in second["duplicates"]] == [first["item"]["name"]]
    assert second["score"] < first["result"]["score"]


def test_fourth_check_hits_the_paywall_before_any_api_call(client, monkeypatch):
    for _ in range(3):
        assert _check(client).status_code == 200

    from app.routers import buy_check

    def boom(*_a, **_k):
        raise AssertionError("no Vision or Claude call after the free limit")

    monkeypatch.setattr(buy_check, "analyze_photo", boom)
    monkeypatch.setattr(buy_check, "judge_purchase", boom)
    res = _check(client)
    assert res.status_code == 402
    assert res.json() == {"paywall": "buy_check", "used": 3, "limit": 3}


def test_pro_skips_the_limit_and_reset_clears_it(client):
    from sqlmodel import Session

    from app.db import engine
    from app.models import AppFlag

    with Session(engine) as s:
        s.add(AppFlag(key="pro", value="1"))
        s.commit()
    for _ in range(4):
        assert _check(client).status_code == 200
    assert _check(client).json()["usage"]["pro"] is True

    client.post("/api/dev/reset")
    res = _check(client)
    assert res.status_code == 200 and res.json()["usage"] == {"checks_used": 1, "limit": 3, "pro": False}


def test_get_returns_a_past_check(client):
    body = _check(client).json()
    again = client.get(f"/api/buy-check/{body['check_id']}").json()
    assert again["result"] == body["result"] and again["item"] == body["item"]
    assert len(again["trace"]) == len(body["trace"])
    assert client.get("/api/buy-check/chk_nope").status_code == 404
    assert client.post("/api/buy-check/chk_nope/keep").status_code == 404


def test_rejects_non_images(client):
    res = client.post("/api/buy-check", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# judge_purchase parsing
# ---------------------------------------------------------------------------
def _req(**kw) -> dc.PurchaseRequest:
    closet = [dc.CandidateItem(name=f"Item {i}", category="tops") for i in range(4)]
    base = dict(
        item=dc.CandidateItem(name="Jacket", category="outerwear", season="fall, winter"),
        closet=closet, outfits=[[0], [1], [2], [3]], duplicates=[0, 1], gaps=["waterproof outerwear"],
        events=[], outfit_count=4, baseline=50,
    )
    return dc.PurchaseRequest(**{**base, **kw})


def _fake_run(answers):
    def run(_op, _body, _fp, _live, _mock):
        return {"answers": answers}, dc.DecisionMeta(source="replay")
    return run


def test_mock_judgment_confirms_duplicates_and_keeps_the_baseline():
    j = dc.judge_purchase(_req())
    assert j.meta.source == "mock"
    assert j.duplicates == [0, 1] and j.adjustment == 0
    assert j.gap_filled == "waterproof outerwear" and j.top_outfits == [0, 1, 2]
    assert j.est_wears_per_year == 25
    assert "overlaps your Item 0 and 1 more" in j.score_reason


def test_judgment_parsing_bounds_and_repairs_answers(monkeypatch):
    monkeypatch.setattr(dc, "_run", _fake_run([
        {"type": "predicate", "name": "dup0", "probability": 0.2},
        {"type": "predicate", "name": "dup1", "probability": 0.9},
        {"type": "text", "name": "gap_filled", "text": "  rain   layer "},
        {"type": "choice", "name": "wears", "choice": "999"},
        {"type": "choice", "name": "pick0", "choice": "2"},
        {"type": "choice", "name": "pick1", "choice": "2"},
        {"type": "choice", "name": "pick2", "choice": "nope"},
        {"type": "score", "name": "adjust", "score": 9.0},
        {"type": "text", "name": "reason", "text": ""},
    ]))
    j = dc.judge_purchase(_req())
    assert j.duplicates == [1]
    assert j.gap_filled == "rain   layer"         # trimmed here; _create collapses inner spaces
    assert j.est_wears_per_year == 25            # unknown choice falls back to the heuristic
    assert j.top_outfits == [2, 0, 1]            # repeated/invalid picks topped up in rule order
    assert j.adjustment == 15                    # out-of-range level clamps to +15
    assert j.score_reason                        # empty reason falls back to the template


@pytest.mark.parametrize("level,adj", [(0, -15), (3, 0), (4, 5), (6, 15)])
def test_adjust_levels_map_to_plus_minus_15(monkeypatch, level, adj):
    monkeypatch.setattr(dc, "_run", _fake_run([{"type": "score", "name": "adjust", "score": float(level)}]))
    assert dc.judge_purchase(_req()).adjustment == adj


def test_text_questions_are_part_of_the_schema():
    body = dc._purchase_body(_req())
    text_q = next(q for q in body["questions"] if q["name"] == "reason")
    schema = dc._question_schema(text_q)
    assert schema["properties"]["text"]["type"] == "string"
    assert "at most 120 characters" in dc._question_text(text_q)
    # Closet pieces go to Claude by index only, never by database id.
    evidence = body["input"][1]["content"][1]["data"]
    assert all("id" not in c for c in evidence["closet"])
