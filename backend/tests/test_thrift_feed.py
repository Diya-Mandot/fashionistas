"""Utah thrift-store feeds: turning Shopify listings into scoreable catalog entries."""

import httpx
import respx

from app.models import CATEGORIES, FORMALITIES
from app.services import catalog as cat
from app.services.thrift_feed import STORES, build_catalog, classify, fetch_store, normalize

HOOD, JAM, LONEPINE, GEARROOM = STORES


def listing(title, product_type="", tags=(), price="40.00", available=True, body="", pid=1, handle="item"):
    return {
        "id": pid, "title": title, "handle": handle, "product_type": product_type, "tags": list(tags),
        "body_html": body, "updated_at": "2026-11-20T10:00:00-07:00",
        "variants": [{"title": "M", "price": price, "available": available}],
        "images": [{"src": "https://cdn.shopify.com/s/files/1/x/files/a.jpg?v=1"}],
    }


def test_classify_prefers_type_and_refines_with_title():
    assert classify("Crewnecks", "Vintage 90s Vancouver Crewneck Sweatshirt") == ("tops", "sweatshirt")
    assert classify("Jackets & Outerwear", "Hooded Fleece Vest") == ("outerwear", "vest")
    assert classify("Quilted Vests", "Striped Neutrals Large Quilted Vest Rework") == ("outerwear", "vest")
    assert classify("t-shirts", "00s Harley Davidson Rhinestone Tank") == ("tops", "t-shirt")
    # A coarse type the title disagrees with on the garment family: trust the store's type.
    assert classify("t-shirts", "Racing Jacket Graphic Tee") == ("tops", "t-shirt")
    assert classify("", "Levi's 501 Jeans Womens 28") == ("bottoms", "jeans")


def test_classify_skips_prints_kids_and_unknowns():
    assert classify("Vintage Prints 9.5x12 Inch", "1950s Fashion Model Knit Cardigan Photo Print") is None
    assert classify("", "1997 Tiger Woods Titleist Poster") is None
    assert classify("Overalls", "OshKosh Denim Overalls Kids 14") is None
    assert classify("T-Shirts", "Nike NFL Eagles Football Jersey Youth XL 18-20") is None
    assert classify("", "Leather Large") is None
    # Adult sizing given alongside a youth size, and words that only look like kids' wear.
    assert classify("Ski & Snow Suits", "90s Columbia Ski Suit – Youth 14/16 (Women's XS)") == ("outerwear", "ski suit")
    assert classify("t-shirts", "90s Billabong Baby Tee") == ("tops", "t-shirt")
    assert classify("t-shirts", "1998 WCW Where The Big Boys Play Tee") == ("tops", "t-shirt")


def test_normalize_maps_to_app_vocabulary():
    e = normalize(JAM, listing("Y2K Dialogue Purple Suede Fringe Jacket Womens L", "Suede Fringe Jackets",
                               tags=["Suede", "Western"], price="89.99", pid=77, handle="dialogue-jacket"))
    assert e["id"] == "thriftjam_77"
    assert e["store"] == "ThriftJam" and e["secondhand"] and not e["sponsored"]
    assert (e["category"], e["subcategory"]) == ("outerwear", "jacket")
    assert e["category"] in CATEGORIES and e["formality"] in FORMALITIES
    assert e["color"] == "purple" and e["material"] == "suede"
    assert e["formality"] == "casual"  # fringe reads casual
    assert e["season"] == "spring, fall"
    assert e["price"] == 89.99 and e["sizes"] == ["M"]
    assert e["url"] == "https://thriftjam.com/products/dialogue-jacket"
    assert e["image"].endswith("?v=1&width=600")


def test_waterproof_only_when_the_listing_says_so():
    ski = normalize(JAM, listing("Vintage 90s Nordica One-Piece Ski Suit – XL", "Ski & Snow Suits"))
    rain = normalize(JAM, listing("Columbia Waterproof Hooded Rain Jacket Navy Mens M", "Jackets & Outerwear"))
    assert not ski["waterproof"] and ski["season"] == "winter"
    assert rain["waterproof"] and rain["color"] == "navy"


def test_normalize_drops_sold_out_and_free_items():
    assert normalize(HOOD, listing("90s Springsteen Tour Tee", "t-shirts", available=False)) is None
    assert normalize(HOOD, listing("90s Springsteen Tour Tee", "t-shirts", price="0.00")) is None
    kept = normalize(HOOD, listing("90s Springsteen Tour Tee", "t-shirts", price="80.00"))
    assert kept["price"] == 80 and kept["material"] == "cotton" and kept["store_location"].endswith("UT")


def test_wool_reads_as_cold_weather():
    e = normalize(JAM, listing("Vintage Pendleton Wool Button Up Shirt Plaid Mens L", "Button-Ups"))
    assert (e["subcategory"], e["material"], e["season"], e["formality"]) == ("shirt", "wool", "fall, winter", "smart casual")


@respx.mock
def test_fetch_store_pages_until_a_short_page():
    page = lambda n: {"products": [listing(f"Tee {i}", "t-shirts", pid=i) for i in range(n)]}
    route = respx.get("https://thrifthood.com/products.json").mock(
        side_effect=[httpx.Response(200, json=page(250)), httpx.Response(200, json=page(3))]
    )
    with httpx.Client() as client:
        raw = fetch_store(HOOD, client, delay_s=0)
    assert len(raw) == 253 and route.call_count == 2
    assert route.calls[1].request.url.params["page"] == "2"


def test_build_catalog_is_sorted_and_scoreable():
    entries = build_catalog([(HOOD, [listing("Black Band Tee", "t-shirts", pid=2), listing("Poster", "", pid=3)]),
                             (JAM, [listing("Navy Wool Overcoat Mens L", "Jackets & Outerwear", pid=1)])])
    assert [e["id"] for e in entries] == ["thrifthood_2", "thriftjam_1"]
    coat = entries[1]
    assert (coat["subcategory"], coat["formality"], coat["season"]) == ("coat", "smart casual", "fall, winter")


def test_thrift_source_reads_thrift_json(tmp_path, monkeypatch):
    from app.config import get_settings

    path = tmp_path / "thrift.json"
    path.write_text('[{"id": "thriftjam_1", "category": "tops", "name": "Tee", "price": 20}]', encoding="utf-8")
    monkeypatch.setattr(cat, "THRIFT_PATH", path)
    monkeypatch.setattr(get_settings(), "catalog_source", "thrift")
    assert [p["id"] for p in cat.load_catalog()] == ["thriftjam_1"]
    monkeypatch.setattr(get_settings(), "catalog_source", "mock")
    assert len(cat.load_catalog()) > 1


def gear(title, product_type, variants, body="", pid=9):
    """A used-gear listing whose variants carry Size / Color / Condition options."""
    return {
        "id": pid, "title": title, "handle": "g", "product_type": product_type, "tags": [], "body_html": body,
        "options": [{"name": "Size"}, {"name": "Color"}, {"name": "Condition"}],
        "variants": [{"title": " / ".join(v[:3]), "option1": v[0], "option2": v[1], "option3": v[2],
                      "price": v[3], "available": v[4]} for v in variants],
        "images": [],
    }


def test_used_variant_store_keeps_only_used_stock():
    shell = gear("Backcountry Women's Gore-Tex Hardshell Jacket", "SKI JACKETS", [
        ("S", "Purple", "Used", "129.89", True), ("M", "Purple", "New", "349.00", True), ("L", "Purple", "Used", "99.00", False),
    ])
    e = normalize(LONEPINE, shell)
    assert (e["category"], e["subcategory"], e["waterproof"]) == ("outerwear", "jacket", True)
    assert e["price"] == 129.89 and e["sizes"] == ["S"] and e["color"] == "purple" and e["style"] == "sporty"
    beanie = gear("Picture Organic Colino Beanie", "WINTER HEADWEAR", [("OS", "Black", "New", "30.00", True)])
    assert normalize(LONEPINE, beanie) is None  # new stock isn't thrift


def test_consignment_store_needs_a_used_description():
    used = listing("Patagonia Rainshell - Women's (M)", "Women's Windbreakers and Rain Jackets",
                   body="<p>Great condition, light signs of wear.</p>")
    new = listing("Black Diamond Mission Glove", "Gloves", body="<p>Description from Black Diamond: warm.</p>")
    e = normalize(GEARROOM, used)
    assert e and e["waterproof"] and e["subcategory"] == "raincoat"
    assert normalize(GEARROOM, new) is None


def test_gear_and_misfiled_listings():
    # Store filed a jacket under SHOES: the title wins.
    assert classify("SHOES", "The North Face Women's Insulated Puffy Jacket") == ("outerwear", "puffer")
    assert classify("SKI PANTS & BIBS", "Flylow Women's Drift Bib") == ("bottoms", "snow pants")
    assert classify("WINTER HEADWEAR", "Outdoor Research Coldfront Down Beanie") == ("accessories", "hat")
    for ptype, title in [("SHOES", "Lange RSJ 65"), ("SHOES", "Rossignol Evo XC 60 R Skin w/ Control Step In Bindings"),
                         ("SKI BOOTS", "Tecnica Mach1 MV 110"), ("Climbing Shoes", "La Sportiva Miura - Women's"),
                         ("JR Outerwear Jackets", "Obermeyer Kids Jacket"), ("Ski - All Mountain", "Atomic Bent 100")]:
        assert classify(ptype, title) is None, title


def test_soft_shell_is_not_waterproof():
    e = normalize(GEARROOM, listing("The North Face Soft Shell Jacket - Men's (M)", "Men's Windbreakers and Rain Jackets",
                                    body="<p>Good condition. Wind-resistant, not a waterproof hardshell.</p>"))
    assert e["category"] == "outerwear" and not e["waterproof"]


def test_partner_picks_credit_the_stylist_gap(monkeypatch):
    """A trip gap (not a closet gap) still lets a matching piece clear the trust rule."""
    from datetime import date

    from app.core import compatibility as compat

    shell = normalize(GEARROOM, listing("Patagonia Rainshell - Women's (M)", "Women's Windbreakers and Rain Jackets",
                                        body="<p>Great condition.</p>", pid=5))
    monkeypatch.setattr(cat, "load_catalog", lambda: (shell,))
    monkeypatch.setattr(cat, "_loaded", {"key": ("test", 1), "products": (shell,)})
    cat._scores.clear()
    from app.seed import closet_items

    rain = compat.Piece(id="r", category="outerwear", name="Old Rain Jacket", subcategory="raincoat", color="yellow",
                        waterproof=True, season="spring, fall")
    closet = [compat.as_piece(i) for i in closet_items()] + [rain]  # no closet gap left for a shell to fill
    plain = cat.score_catalog(closet, [], date(2026, 11, 20))[0]
    assert plain.score < cat.TRUST_MIN and not plain.assessment.gaps_filled
    picks = cat.partner_picks("waterproof outer layer", closet, [], date(2026, 11, 20))
    assert [p["id"] for p in picks] == ["gearroom_5"]
    assert picks[0]["fills"] == ["waterproof outer layer"]
    assert picks[0]["score"] == plain.score + compat.GAP_BONUS >= cat.TRUST_MIN
    cat._scores.clear()
