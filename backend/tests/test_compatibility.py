"""Unit tests for the pure compatibility engine (no DB, no network)."""

from datetime import date

import pytest

from app.core import compatibility as c
from app.core.compatibility import Piece

TODAY = date(2026, 11, 20)


def piece(id_: str, category: str, **kw) -> Piece:
    return Piece(id=id_, category=category, **kw)


def tiny_closet() -> list[Piece]:
    return [
        piece("t1", "tops", name="White tee", subcategory="t-shirt", color="white", season="all season"),
        piece("t2", "tops", name="Grey sweater", subcategory="sweater", color="grey", season="fall, winter"),
        piece("b1", "bottoms", name="Jeans", subcategory="jeans", color="denim", season="all season"),
        piece("b2", "bottoms", name="Linen shorts", subcategory="shorts", color="beige", season="summer"),
        piece("s1", "shoes", name="Sneakers", subcategory="sneakers", color="white", season="all season"),
        piece("s2", "shoes", name="Pumps", subcategory="heels", color="black", formality="formal", season="all season"),
        piece("o1", "outerwear", name="Denim jacket", subcategory="jacket", color="light blue", season="spring, fall"),
    ]


# ---------------------------------------------------------------------------
# Outfits
# ---------------------------------------------------------------------------
def test_outerwear_layers_over_every_valid_base_outfit():
    coat = piece("new", "outerwear", subcategory="coat", color="black", season="fall, winter")
    count, best = c.count_outfits(coat, tiny_closet(), TODAY)
    # Valid bases: 2 tops x jeans x sneakers. Shorts are summer-only (no overlap
    # with a fall/winter coat) and the formal pumps are two steps from casual.
    assert count == 2
    assert all("new" in [p.id for p in o.items] for o in best)
    assert {frozenset(p.id for p in o.items) for o in best} == {
        frozenset({"t1", "b1", "s1", "new"}), frozenset({"t2", "b1", "s1", "new"}),
    }


def test_new_bottom_fills_the_bottom_slot():
    trousers = piece("new", "bottoms", subcategory="trousers", color="black", season="all season")
    count, best = c.count_outfits(trousers, tiny_closet(), TODAY)
    assert count == 2  # either top, with sneakers
    for o in best:
        assert [p.category for p in o.items] == ["tops", "bottoms", "shoes"]


def test_color_clash_and_season_rules_exclude_outfits():
    closet = [
        piece("t1", "tops", color="red", season="all season"),
        piece("t2", "tops", color="green", season="summer"),
        piece("s1", "shoes", color="purple", season="all season"),
        piece("s2", "shoes", color="black", season="all season"),
    ]
    winter_skirt = piece("new", "bottoms", color="orange", season="winter")
    count, best = c.count_outfits(winter_skirt, closet, TODAY)
    # t2 is summer-only; red + orange + purple is three accents. Only red top + black shoes passes.
    assert count == 1
    assert {p.id for p in best[0].items} == {"t1", "new", "s2"}


def test_a_formal_coat_may_layer_over_smart_casual_but_not_casual_clothes():
    closet = [
        piece("t1", "tops", formality="smart casual"),
        piece("t2", "tops", formality="casual", style="casual"),
        piece("b1", "bottoms", formality="smart casual"),
        piece("s1", "shoes", formality="smart casual"),
    ]
    coat = piece("new", "outerwear", subcategory="coat", formality="formal", style="smart casual")
    count, _ = c.count_outfits(coat, closet, TODAY)
    assert count == 1  # the casual tee is three steps from formal


def test_the_item_itself_is_never_counted_twice():
    closet = tiny_closet()
    count_owned, _ = c.count_outfits(closet[0], closet, TODAY)
    count_new, _ = c.count_outfits(piece("new", **{k: getattr(closet[0], k) for k in ("category", "color", "season")}), closet[1:], TODAY)
    assert count_owned == count_new


def test_unknown_category_has_no_outfits():
    assert c.count_outfits(piece("new", "lingerie"), tiny_closet(), TODAY) == (0, [])


def test_count_label_caps_at_50():
    assert c.outfit_count_label(12) == "12"
    assert c.outfit_count_label(50) == "50"
    assert c.outfit_count_label(51) == "50+"


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------
def test_duplicates_need_category_shade_and_silhouette():
    closet = [
        piece("a", "outerwear", name="Black biker", subcategory="jacket", color="black"),
        piece("b", "outerwear", name="Black bomber", subcategory="bomber", color="jet black"),
        piece("c", "outerwear", name="Black blazer", subcategory="blazer", color="black"),
        piece("d", "outerwear", name="Navy jacket", subcategory="jacket", color="navy"),
        piece("e", "tops", name="Black tee", subcategory="jacket", color="black"),
    ]
    new = piece("new", "outerwear", subcategory="jacket", color="black")
    dups = c.find_duplicates(new, closet)
    assert [d.item.id for d in dups] == ["a", "b"]  # bomber is an alias of jacket; navy is not black
    assert dups[0].reason == "also a black jacket"


def test_other_subcategory_never_matches():
    closet = [piece("a", "accessories", subcategory="other", color="gold")]
    assert c.find_duplicates(piece("new", "accessories", subcategory="other", color="gold"), closet) == []


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------
def test_gap_filled_versus_not_filled():
    gaps = c.find_gaps(tiny_closet())
    labels = {g.label for g in gaps}
    assert {"waterproof outerwear", "dark tailored trousers", "formal outerwear"} <= labels
    rain = piece("new", "outerwear", subcategory="raincoat", waterproof=True)
    assert "waterproof outerwear" in c.gaps_filled(rain, gaps)
    assert c.gaps_filled(piece("new", "outerwear", subcategory="jacket", color="light blue", season="spring, fall"), gaps) == []


def test_dark_tailored_trousers_need_dark_and_not_casual():
    gaps = c.find_gaps(tiny_closet())
    navy = piece("new", "bottoms", subcategory="pants", color="navy", formality="business")
    khaki = piece("new", "bottoms", subcategory="trousers", color="khaki", formality="business")
    sweats = piece("new", "bottoms", subcategory="trousers", color="black", formality="casual")
    assert "dark tailored trousers" in c.gaps_filled(navy, gaps)
    assert "dark tailored trousers" not in c.gaps_filled(khaki, gaps)
    assert "dark tailored trousers" not in c.gaps_filled(sweats, gaps)


def test_thin_slots_are_gaps_too():
    closet = [p for p in tiny_closet() if p.id != "s2"]  # one neutral pair of shoes left
    gap = next(g for g in c.find_gaps(closet) if g.label == "neutral shoes")
    assert (gap.count, gap.status) == (1, "thin")


def test_calendar_gaps_only_appear_with_the_event():
    assert "formal evening outfit" not in {g.label for g in c.find_gaps(tiny_closet())}
    gala = [{"name": "Museum gala", "date": "2026-11-28", "dress_code_hint": "formal"}]
    assert "formal evening outfit" in {g.label for g in c.find_gaps(tiny_closet(), gala)}


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
EVENTS = [
    {"name": "Team dinner", "date": "2026-11-27", "dress_code_hint": "dressy-casual evening"},
    {"name": "Wedding", "date": "2026-12-05", "dress_code_hint": "formal"},
    {"name": "Yoga", "date": "2026-11-22", "dress_code_hint": "athletic"},
    {"name": "Last week's party", "date": "2026-11-13", "dress_code_hint": "dressy-casual evening"},
    {"name": "Far-off dinner", "date": "2027-02-01", "dress_code_hint": "dressy-casual evening"},
]


def test_calendar_matches_dress_code_window_and_season():
    jacket = piece("new", "outerwear", formality="smart casual", season="fall, winter")
    assert c.calendar_matches(jacket, EVENTS, TODAY) == [{"event": "Team dinner", "date": "2026-11-27"}]
    summer_dress = piece("new", "dresses", formality="formal", season="summer")
    assert c.calendar_matches(summer_dress, EVENTS, TODAY) == []  # dinner and wedding are in fall/winter
    leggings = piece("new", "activewear", season="all season")
    assert [m["event"] for m in c.calendar_matches(leggings, EVENTS, TODAY)] == ["Yoga"]


# ---------------------------------------------------------------------------
# Score and verdict
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("score,expected", [(0, "skip"), (39, "skip"), (40, "maybe"), (69, "maybe"), (70, "great_buy"), (100, "great_buy")])
def test_verdict_boundaries(score, expected):
    assert c.verdict(score) == expected


def test_baseline_score_parts_and_caps():
    assert c.baseline_score(0, False, 0, 0) == 20
    assert c.baseline_score(4, False, 0, 0) == 32
    assert c.baseline_score(100, False, 0, 0) == 60          # outfits cap at +40
    assert c.baseline_score(0, True, 0, 0) == 45
    assert c.baseline_score(0, False, 10, 0) == 35           # events cap at +15
    assert c.baseline_score(20, False, 1, 1) == 45


def test_baseline_score_clamps_to_0_100():
    assert c.baseline_score(0, False, 0, 5) == 0             # duplicates cap at -40, then clamp
    assert c.baseline_score(100, True, 10, 0) == 100


def test_assess_combines_everything():
    closet = tiny_closet()
    jacket = piece("new", "outerwear", subcategory="jacket", color="light blue", season="spring, fall")
    a = c.assess(jacket, closet, EVENTS, TODAY)
    assert [d.item.id for d in a.duplicates] == ["o1"]
    assert a.gaps_filled == []
    assert a.score == c.baseline_score(a.outfit_count, False, len(a.calendar_matches), 1)
    assert a.verdict == c.verdict(a.score)


def test_as_piece_reads_rows_and_catalog_dicts():
    from app.models import WardrobeItem

    row = WardrobeItem(id="itm_x", name="Tee", category="tops", color="white", number_of_times_worn=4)
    assert c.as_piece(row).times_worn == 4
    p = c.as_piece({"id": "p_1", "name": "Shell", "category": "Outerwear", "waterproof": True, "price": 50})
    assert (p.category, p.waterproof, p.subcategory) == ("outerwear", True, "other")


# ---------------------------------------------------------------------------
# Against the real demo closet
# ---------------------------------------------------------------------------
def test_seed_closet_shows_the_demo_gaps():
    from app.seed import closet_items

    labels = {g.label for g in c.find_gaps([c.as_piece(i) for i in closet_items()])}
    assert {"waterproof outerwear", "dark tailored trousers", "formal outerwear"} <= labels
