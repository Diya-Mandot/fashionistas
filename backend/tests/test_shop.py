"""Shop Your Gaps and partner picks, scored against the seed closet (no Claude)."""

from datetime import date

import pytest

from app.core import compatibility as compat
from app.services import catalog as cat

TODAY = date(2026, 11, 20)
CATALOG = {p["id"]: p for p in cat.load_catalog()}
SPONSORED = [p for p in CATALOG.values() if p["sponsored"]]


@pytest.fixture(scope="module")
def closet():
    from app.seed import closet_items

    return [compat.as_piece(i) for i in closet_items()]


@pytest.fixture(scope="module")
def full(closet):
    return cat.shop(closet, [], TODAY)


def test_trust_rule_hides_everything_under_70(closet, full):
    all_scored = cat.score_products(list(CATALOG.values()), closet, [], TODAY)
    low = {s.product["id"] for s in all_scored if s.score < cat.TRUST_MIN}
    shown = {p["id"] for p in full["products"]}
    assert shown and not shown & low
    assert all(p["score"] >= 70 and p["verdict"] == "great_buy" for p in full["products"])
    assert full["hidden_by_trust_rule"] == len(low) == len(CATALOG) - len(shown)


def test_sponsored_items_follow_the_same_rule(full):
    shown = {p["id"]: p for p in full["products"]}
    shown_sponsored = [p for p in SPONSORED if p["id"] in shown]
    hidden_sponsored = [p for p in SPONSORED if p["id"] not in shown]
    assert shown_sponsored, "the demo needs one sponsored product that earns its place"
    assert hidden_sponsored, "the demo needs one sponsored product the trust rule hides"
    assert all(shown[p["id"]]["sponsored"] is True for p in shown_sponsored)


def test_ranking_outfits_then_gap_then_price(full):
    keys = [(-min(p["outfit_count"], compat.OUTFIT_DISPLAY_CAP + 1), not p["fills"], p["price"]) for p in full["products"]]
    assert keys == sorted(keys)


def test_category_filter_and_max_price(closet):
    outer = cat.shop(closet, [], TODAY, category="outerwear")
    assert outer["products"] and all(p["category"] == "outerwear" for p in outer["products"])
    n_outer = sum(1 for p in CATALOG.values() if p["category"] == "outerwear")
    assert len(outer["products"]) + outer["hidden_by_trust_rule"] == n_outer
    cheap = cat.shop(closet, [], TODAY, max_price=100)
    assert all(p["price"] <= 100 for p in cheap["products"])
    assert cat.shop(closet, [], TODAY, category="nonsense")["products"] == []


def test_gap_summary_counts_shown_fillers(full):
    gaps = {g["label"]: g for g in full["gaps"]}
    assert {"waterproof outerwear", "dark tailored trousers", "formal outerwear"} <= set(gaps)
    for label, g in gaps.items():
        assert g["products"] == sum(1 for p in full["products"] if label in p["fills"])
    assert gaps["waterproof outerwear"]["status"] == "empty" and gaps["waterproof outerwear"]["products"] >= 1


def test_calendar_needs_join_the_gap_list(closet):
    gala = [{"name": "Museum gala", "date": "2026-11-28", "dress_code_hint": "formal"}]
    labels = {g["label"] for g in cat.shop(closet, gala, TODAY)["gaps"]}
    assert "formal evening outfit" not in labels  # the seed closet already has formal dresses
    no_dresses = [p for p in closet if p.category != "dresses"]
    assert "formal evening outfit" in {g["label"] for g in cat.shop(no_dresses, gala, TODAY)["gaps"]}


@pytest.mark.parametrize("need,category,waterproof", [
    ("waterproof outer layer", "outerwear", True),
    ("Rain jacket", "outerwear", True),
    ("water-resistant shoes", "shoes", True),
    ("shoes", "shoes", None),
])
def test_partner_picks_match_the_gap(closet, need, category, waterproof):
    picks = cat.partner_picks(need, closet, today=TODAY)
    assert 1 <= len(picks) <= 2
    for p in picks:
        assert p["category"] == category and p["score"] >= cat.TRUST_MIN
        if waterproof:
            assert p["waterproof"] is True


def test_partner_picks_for_unknown_or_unstocked_needs(closet):
    assert cat.partner_picks("a sense of adventure", closet, today=TODAY) == []
    assert cat.partner_picks("formal evening outfit", closet, today=TODAY) == []  # no formal dresses in stock


def test_shop_endpoint(client):
    res = client.get("/api/shop", params={"category": "outerwear"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"gaps", "products", "hidden_by_trust_rule", "categories", "trust_min"}
    assert body["products"] and all(p["category"] == "outerwear" for p in body["products"])
    p = body["products"][0]
    assert {"outfit_count", "outfit_count_label", "fills", "score", "verdict", "sponsored", "store", "price"} <= set(p)
    assert client.get("/api/shop", params={"max_price": -1}).status_code == 422
