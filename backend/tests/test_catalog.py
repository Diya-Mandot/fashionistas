"""The mock Shop Your Gaps catalog and the demo closet it is stacked against."""

import json
from collections import Counter
from pathlib import Path

from app.core import outfit_generator as gen
from app.models import CATEGORIES, FORMALITIES, STYLES
from app.seed import closet_items

BACKEND = Path(__file__).resolve().parent.parent
CATALOG = json.loads((BACKEND / "catalog" / "catalog.json").read_text(encoding="utf-8"))
REQUIRED = ("id", "name", "store", "price", "image", "category", "subcategory", "color", "style",
            "formality", "season", "material", "waterproof", "sponsored", "demo_role", "credit")
DEMO_GAPS = {"waterproof outerwear", "dark tailored trousers", "formal outerwear"}


def test_catalog_size_and_unique_ids():
    assert 25 <= len(CATALOG) <= 40
    assert len({p["id"] for p in CATALOG}) == len(CATALOG)


def test_every_item_uses_app_vocabulary():
    for p in CATALOG:
        missing = [k for k in REQUIRED if k not in p]
        assert not missing, f"{p['id']} missing {missing}"
        assert p["category"] in CATEGORIES, p["id"]
        assert p["formality"] in FORMALITIES, p["id"]
        assert p["style"] in STYLES, p["id"]
        assert gen.parse_seasons(p["season"]), f"{p['id']}: unreadable season {p['season']!r}"
        assert isinstance(p["price"], (int, float)) and p["price"] > 0
        assert p["demo_role"] in ("gap_filler", "good_fit", "poor_fit")


def test_every_image_exists_and_is_credited():
    for p in CATALOG:
        assert p["image"] == f"/media/catalog/{p['id']}.jpg"
        assert (BACKEND / "catalog" / "images" / f"{p['id']}.jpg").is_file(), p["id"]
        assert p["credit"]["license"] and p["credit"]["source_url"].startswith("https://commons.wikimedia.org/")


def test_catalog_is_stacked_for_the_demo():
    roles = Counter(p["demo_role"] for p in CATALOG)
    assert roles["gap_filler"] >= 6 and roles["poor_fit"] >= 5
    # Each demo gap has at least two products that fill it.
    fills = Counter(p.get("fills") for p in CATALOG if p["demo_role"] == "gap_filler")
    assert all(fills[g] >= 2 for g in DEMO_GAPS), fills
    # One sponsored item that should be shown and one the trust rule must hide.
    sponsored = [p for p in CATALOG if p["sponsored"]]
    assert any(p["demo_role"] != "poor_fit" for p in sponsored)
    assert any(p["demo_role"] == "poor_fit" for p in sponsored)


def test_demo_closet_really_has_the_gaps():
    closet = closet_items()
    outer = [i for i in closet if i.category == "outerwear"]
    assert not any(i.waterproof for i in outer)
    assert not any(i.formality == "formal" for i in outer)
    dark = ("black", "charcoal", "navy", "grey", "gray")
    assert not any(i.subcategory == "trousers" and any(d in (i.color or "") for d in dark) for i in closet if i.category == "bottoms")


def test_demo_closet_has_two_black_jackets_for_the_duplicate_warning():
    black_outer = [i.name for i in closet_items() if i.category == "outerwear" and (i.color or "").startswith("black")]
    assert len(black_outer) >= 2, black_outer


def test_catalog_images_are_served(client):
    r = client.get(CATALOG[0]["image"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
