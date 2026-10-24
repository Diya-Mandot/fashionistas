"""Unit tests for the pure rules-based outfit generator (no DB, no network)."""

from datetime import date, timedelta

import pytest

from app.core.outfit_generator import (
    MAX_ITEMS,
    MIN_ITEMS,
    SHOELESS_PENALTY,
    ItemData,
    WeatherContext,
    color_family,
    color_harmony,
    diversify,
    filter_for_weather,
    generate_candidates,
    item_slots,
    normalize_style,
    parse_exclude,
    parse_seasons,
    parse_styles_override,
    stored_style_tags,
    style_coherence,
    template_copy,
)

TODAY = date(2026, 10, 1)


def item(n: int, category: str, **kw) -> ItemData:
    return ItemData(id=f"00000000-0000-0000-0000-{n:012d}", category=category, **kw)


def closet() -> list[ItemData]:
    return [
        item(1, "tops", name="White tee", color="white"),
        item(2, "tops", name="Blue shirt", color="light blue", style="smart casual"),
        item(3, "bottoms", name="Jeans", color="denim"),
        item(4, "bottoms", name="Chinos", color="khaki", style="smart casual"),
        item(5, "shoes", name="Sneakers", color="white"),
        item(6, "shoes", name="Loafers", color="brown", style="smart casual"),
        item(7, "dresses", name="Slip dress", color="black", season="all season"),
        item(8, "outerwear", name="Wool coat", color="camel", season="fall/winter"),
        item(9, "bags", name="Tote", color="beige"),
        item(10, "accessories", name="Scarf", color="red"),
    ]


def _slot_counts(items):
    counts = {}
    for i in items:
        cat = i.category
        counts[cat] = counts.get(cat, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def test_only_valid_templates_are_produced():
    candidates = generate_candidates(closet(), WeatherContext(temp_f=60), today=TODAY, seed=1)
    assert candidates
    for cand in candidates:
        counts = _slot_counts(cand.items)
        assert MIN_ITEMS <= len(cand.items) <= MAX_ITEMS
        assert len(set(cand.item_ids)) == len(cand.item_ids)
        assert counts.get("outerwear", 0) <= 1
        assert counts.get("bags", 0) + counts.get("accessories", 0) <= 1
        assert counts.get("shoes", 0) == 1
        if counts.get("dresses"):
            assert counts["dresses"] == 1
            assert not counts.get("tops") and not counts.get("bottoms")
        else:
            assert counts.get("tops") == 1 and counts.get("bottoms") == 1


def test_activewear_can_fill_top_and_bottom_but_not_both_with_one_piece():
    items = [
        item(1, "activewear", name="Sports bra", subcategory="sports bra", style="sporty"),
        item(2, "activewear", name="Leggings", subcategory="leggings", style="sporty"),
        item(3, "activewear", name="Track piece", style="sporty"),  # ambiguous -> either slot
        item(4, "shoes", name="Trainers", style="sporty"),
    ]
    assert item_slots(items[0]) == {"top"}
    assert item_slots(items[1]) == {"bottom"}
    assert item_slots(items[2]) == {"top", "bottom"}

    candidates = generate_candidates(items, today=TODAY, seed=1)
    keys = {c.key for c in candidates}
    assert frozenset({items[0].id, items[1].id, items[3].id}) in keys
    for cand in candidates:
        assert len(cand.items) >= 3  # top + bottom + shoes, never one piece twice


def test_shoeless_combos_allowed_only_when_closet_has_no_shoes():
    no_shoes = [i for i in closet() if i.category != "shoes"]
    candidates = generate_candidates(no_shoes, today=TODAY, seed=1)
    assert candidates
    assert all(c.shoeless for c in candidates)
    assert all(len(c.items) >= MIN_ITEMS for c in candidates)

    with_shoes = generate_candidates(closet(), today=TODAY, seed=1)
    assert not any(c.shoeless for c in with_shoes)
    assert SHOELESS_PENALTY > 0


def test_too_few_items_produce_no_candidates():
    assert generate_candidates([item(1, "tops"), item(2, "shoes")], today=TODAY, seed=1) == []
    assert generate_candidates([], today=TODAY, seed=1) == []


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def test_color_family_normalization():
    assert color_family("Navy Blue") == "neutral"
    assert color_family("off-white") == "neutral"
    assert color_family("light blue") == "blue"
    assert color_family("Burgundy") == "red"
    assert color_family("floral print") == "multi"
    assert color_family(None) == "neutral"
    assert color_family("sparkly mystery") == "neutral"


def test_color_harmony_prefers_neutrals_with_one_accent_and_penalizes_many_accents():
    neutral = [item(1, "tops", color="black"), item(2, "bottoms", color="denim")]
    one_accent = [item(1, "tops", color="red"), item(2, "bottoms", color="denim")]
    three_accents = [
        item(1, "tops", color="red"), item(2, "bottoms", color="green"), item(3, "shoes", color="yellow"),
    ]
    assert color_harmony(one_accent) > color_harmony(neutral) > color_harmony(three_accents)
    assert color_harmony(three_accents) < 0


def test_style_coherence_penalizes_clashing_styles():
    same = [item(1, "tops", style="formal"), item(2, "bottoms", style="Formal")]
    compatible = [item(1, "tops", style="formal"), item(2, "bottoms", style="smart casual")]
    clash = [item(1, "tops", style="formal"), item(2, "bottoms", style="sporty")]
    assert style_coherence(same) > style_coherence(compatible) > style_coherence(clash)
    # Missing style is treated as casual.
    assert style_coherence([item(1, "tops"), item(2, "bottoms", style="casual")]) == 1.0


def test_cold_weather_prefers_outerwear():
    candidates = generate_candidates(closet(), WeatherContext(temp_f=40), today=TODAY, seed=3)
    assert any(i.category == "outerwear" for i in candidates[0].items)


def test_rarely_worn_items_rank_higher_all_else_equal():
    worn = item(1, "tops", color="white", last_worn=TODAY - timedelta(days=1), times_worn=40)
    fresh = item(2, "tops", color="white", last_worn=None, times_worn=0)
    rest = [item(3, "bottoms", color="denim"), item(4, "shoes", color="black")]
    candidates = generate_candidates([worn, fresh, *rest], today=TODAY, seed=5)
    assert fresh.id in candidates[0].item_ids


# ---------------------------------------------------------------------------
# Weather filter
# ---------------------------------------------------------------------------
def test_weather_filter_is_lenient_but_drops_clear_mismatches():
    summer_dress = item(1, "dresses", season="Summer")
    coat = item(2, "outerwear", season="winter")
    unknown = item(3, "tops", season=None)
    garbage = item(4, "tops", season="whenever")

    assert summer_dress not in filter_for_weather([summer_dress], WeatherContext(temp_f=30))
    assert coat not in filter_for_weather([coat], WeatherContext(temp_f=95))
    assert coat in filter_for_weather([coat], WeatherContext(temp_f=95, precipitation=True))
    assert filter_for_weather([unknown, garbage], WeatherContext(temp_f=95)) == [unknown, garbage]
    assert filter_for_weather([summer_dress, coat], WeatherContext()) == [summer_dress, coat]
    assert parse_seasons("All Season") == {"all"}
    assert parse_seasons("Fall/Winter") == {"fall", "winter"}


# ---------------------------------------------------------------------------
# Determinism, exclusion, diversity
# ---------------------------------------------------------------------------
def test_same_seed_is_deterministic_regardless_of_input_order():
    items = closet()
    a = generate_candidates(items, WeatherContext(temp_f=60), today=TODAY, seed=42)
    b = generate_candidates(list(reversed(items)), WeatherContext(temp_f=60), today=TODAY, seed=42)
    assert [(c.item_ids, c.score) for c in a] == [(c.item_ids, c.score) for c in b]


def test_excluded_sets_are_skipped():
    first = generate_candidates(closet(), today=TODAY, seed=1)[0]
    again = generate_candidates(closet(), today=TODAY, seed=1, exclude=[first.key])
    assert first.key not in {c.key for c in again}


def test_diversify_spreads_item_usage():
    ranked = generate_candidates(closet(), today=TODAY, seed=1)
    picked = diversify(ranked, 5)
    top_five = ranked[:5]

    def max_reuse(cands):
        counts = {}
        for c in cands:
            for i in c.item_ids:
                counts[i] = counts.get(i, 0) + 1
        return max(counts.values())

    assert len(picked) == 5
    assert len({c.key for c in picked}) == 5
    assert max_reuse(picked) <= max_reuse(top_five)


def test_diversify_returns_all_when_fewer_than_k():
    ranked = generate_candidates(closet()[:2] + [closet()[2], closet()[4]], today=TODAY, seed=1)
    assert len(diversify(ranked, 20)) == len(ranked)


# ---------------------------------------------------------------------------
# Legacy exclude + template copy
# ---------------------------------------------------------------------------
def test_parse_exclude_ignores_malformed_parts():
    a = "00000000-0000-0000-0000-000000000001"
    b = "00000000000000000000000000000002"  # hex form normalizes to dashed
    parsed = parse_exclude(f"{a},{b}|not-a-uuid,{a}|,,|{a}")
    assert parsed == [frozenset({a, "00000000-0000-0000-0000-000000000002"})]
    assert parse_exclude(None) == []


def test_template_copy_respects_limits():
    long_name = item(1, "outerwear", name="X" * 500, color="camel")
    rest = [item(2, "tops"), item(3, "bottoms"), item(4, "shoes")]
    cand = generate_candidates([long_name, *rest], WeatherContext(temp_f=30), today=TODAY, seed=1)[0]
    vibe, tip = template_copy(cand, WeatherContext(temp_f=30), TODAY)
    assert 0 < len(vibe) <= 40
    assert 0 < len(tip) <= 200


def test_unnamed_items_use_singular_category_nouns_in_tips():
    from app.core.outfit_generator import _short_name

    assert _short_name(item(1, "dresses")) == "dress"
    assert _short_name(item(2, "accessories")) == "accessory"
    assert _short_name(item(3, "tops", name="  ")) == "top"


def test_unnamed_items_use_their_subcategory_in_tips():
    from app.core.outfit_generator import _short_name

    assert _short_name(item(1, "dresses", subcategory="jumpsuit")) == "jumpsuit"
    assert _short_name(item(2, "dresses", subcategory="overalls")) == "overalls"
    assert _short_name(item(3, "dresses", subcategory="other")) == "dress"
    assert _short_name(item(4, "dresses", name="Red jumpsuit", subcategory="jumpsuit")) == "Red jumpsuit"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("business", "smart casual"), (" Trendy ", "streetwear"), ("formal", "formal"), (None, "casual")],
)
def test_normalize_style_maps_retired_tags(raw, expected):
    assert normalize_style(raw) == expected


def test_stored_style_tags_include_retired_tags_for_allowed_styles():
    assert stored_style_tags({"formal", "smart casual"}) == {"formal", "smart casual", "business"}
    assert stored_style_tags({"streetwear"}) == {"streetwear", "trendy"}
    assert stored_style_tags({"sporty"}) == {"sporty"}


def test_styles_override_maps_retired_tags():
    assert parse_styles_override("Business,Trendy") == {"smart casual", "streetwear"}


def test_retired_and_current_tags_count_as_one_style():
    items = [
        item(1, "tops", style="business"),
        item(2, "bottoms", style="smart casual"),
    ]
    assert style_coherence(items) == 1
