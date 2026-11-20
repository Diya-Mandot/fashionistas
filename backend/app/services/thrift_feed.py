"""Real secondhand inventory from Utah thrift and used-gear stores that sell online.

Every store here runs on Shopify, which publishes each storefront's catalog at
/products.json (title, type, tags, variants with price and stock, photos).
We page through that public feed, keep in-stock secondhand clothing, and turn
each listing into a catalog entry in the app's vocabulary (category,
subcategory, color, formality, season, material, waterproof) so the
compatibility engine can score it like any other product. No Claude call:
rules only, so a sync is free and repeatable.

Some stores sell new stock alongside used, so each store says how to tell a
used listing apart (see Store.condition).

    STORES -> fetch_store() -> normalize() -> catalog/thrift.json
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional

import httpx

# How a store marks secondhand stock:
#   all            - everything it sells is secondhand (thrift / vintage shops)
#   used_variant   - each variant names its condition ("L / Black / Used"); keep the Used ones
#   described_used - a consignment shop that also stocks new gear; keep listings whose
#                    description talks about condition or prior use
Condition = Literal["all", "used_variant", "described_used"]


@dataclass(frozen=True)
class Store:
    key: str       # id prefix, stable across syncs
    name: str      # shown on product cards
    domain: str
    location: str  # where the physical shop is
    condition: Condition = "all"
    style: str = "vintage"


STORES: tuple[Store, ...] = (
    Store("thrifthood", "Thrifthood", "thrifthood.com", "Salt Lake City & Provo, UT"),
    Store("thriftjam", "ThriftJam", "thriftjam.com", "Utah (mobile thrift bus)"),
    Store("lonepine", "Lone Pine Gear Exchange", "lonepinegearx.com", "Millcreek, UT",
          condition="used_variant", style="sporty"),
    Store("gearroom", "The Gear Room", "thegearroom.com", "Cottonwood Heights, UT",
          condition="described_used", style="sporty"),
)

PAGE_SIZE = 250  # Shopify's max for /products.json
MAX_PAGES = 40
USER_AGENT = "fashionistas-thrift-sync/0.1"
IMAGE_WIDTH = 600


def fetch_store(store: Store, client: httpx.Client, delay_s: float = 1.0) -> list[dict[str, Any]]:
    """Every listing in a store's public Shopify feed, raw. Polite: one page at a time."""
    products: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        r = client.get(f"https://{store.domain}/products.json", params={"limit": PAGE_SIZE, "page": page})
        r.raise_for_status()
        batch = r.json().get("products") or []
        products.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(delay_s)
    return products


# ---------------------------------------------------------------------------
# Classification: product type first, then title keywords
# ---------------------------------------------------------------------------
# Product types that are never adult clothing, whatever the title says.
_SKIP_TYPES = ("vintage prints", "baby jam", "kids", "jr ", "junior", "climbing shoe")
# Types that are gear rather than clothing. Checked only when no clothing rule matched
# the type, because "ski jackets" and "ski pants & bibs" are clothing.
_GEAR_TYPES = ("ski", "snowboard", "splitboard", "binding", "boot", "pole", "helmet", "goggle", "skin", "safety",
               "tuning", "refill", "luggage", "climbing", "carabiner", "belay", "rope", "ice ", "crampon", "shovel",
               "beacon", "headlamp", "guidebook", "food", "sticker", "socks", "footbed", "repair", "dry bag",
               "placeholder", "merch")
# Non-clothing words, only checked when the product type doesn't already say what it is.
_SKIP_WORDS = ("framed", "magazine ad", "poster", "sticker", "mug", "blanket", "pillow", "gift card",
               "mystery box", "bundle")
# Gear that stores file under clothing types ("Lange RSJ 65" under SHOES): always skipped.
_GEAR_WORDS = ("binding", "bindings", "skis", "ski boot", "ski boots", "snowboard boot", "snowboard boots",
               "climbing shoe", "climbing shoes", "lange", "leash", "leashes", "sealant")
# Children's sizes: skipped unless the listing also gives an adult size ("Youth 14/16 (Women's XS)").
_KID_SIZE = re.compile(
    r"(\b(youth|toddler|kids?|girls|boys|baby|junior'?s|jr)\s+(size\s+)?(\d|xs\b|s\b|m\b|l\b|xl\b)|"
    r"\b\d{1,2}-\d{1,2}m\b|\b\d{1,2}t\b|\bkid'?s\b|\bjunior'?s\b)"
    r"(?!.*\b(wo)?men'?s\b)"
)

# (keyword in product type, category, subcategory). First match wins.
_TYPE_RULES: tuple[tuple[str, str, str], ...] = (
    ("ski & snow", "outerwear", "ski suit"),
    ("ski pants", "bottoms", "snow pants"),
    ("winter pants", "bottoms", "snow pants"),
    ("base layer bottom", "bottoms", "leggings"),
    ("base layer top", "tops", "base layer"),
    ("baselayer", "tops", "base layer"),
    ("ski jacket", "outerwear", "jacket"),
    ("winter shell", "outerwear", "jacket"),
    ("insulated shell", "outerwear", "jacket"),
    ("winter coat", "outerwear", "coat"),
    ("puffy", "outerwear", "puffer"),
    ("softshell", "outerwear", "jacket"),
    ("windbreaker", "outerwear", "jacket"),
    ("rainwear", "outerwear", "jacket"),
    ("rain jacket", "outerwear", "jacket"),
    ("fleece", "outerwear", "jacket"),
    ("suede fringe", "outerwear", "jacket"),
    ("leather jacket", "outerwear", "jacket"),
    ("denim jacket", "outerwear", "jacket"),
    ("quilted vest", "outerwear", "vest"),
    ("vest", "outerwear", "vest"),
    ("jacket", "outerwear", "jacket"),
    ("outerwear", "outerwear", "jacket"),
    ("crewneck", "tops", "sweatshirt"),
    ("hoodie", "tops", "hoodie"),
    ("sweatshirt", "tops", "sweatshirt"),
    ("sweater", "tops", "sweater"),
    ("t-shirt", "tops", "t-shirt"),
    ("tanktop", "tops", "t-shirt"),
    ("button-up", "tops", "shirt"),
    ("western shirt", "tops", "shirt"),
    ("cut shirt", "tops", "shirt"),
    ("tie top", "tops", "blouse"),
    ("corset", "tops", "top"),
    ("performance shirt", "tops", "top"),
    ("shirts", "tops", "top"),
    ("tops", "tops", "top"),
    ("overalls", "bottoms", "overalls"),
    ("shorts", "bottoms", "shorts"),
    ("skirt", "bottoms", "skirt"),
    ("pants", "bottoms", "trousers"),
    ("bottoms", "bottoms", "trousers"),
    ("dress", "dresses", "dress"),
    ("running shoe", "shoes", "sneakers"),
    ("shoes", "shoes", "other"),
    ("handbag", "bags", "handbag"),
    ("backpack", "bags", "backpack"),
    ("hip pack", "bags", "backpack"),
    ("bag", "bags", "handbag"),
    ("winter headwear", "accessories", "hat"),
    ("glove", "accessories", "gloves"),
    ("hats", "accessories", "hat"),
    ("accessories", "accessories", "other"),
)

# Title keywords, checked in order: specific garments before generic ones, so a
# "hooded jacket" is a jacket and a "t-shirt dress" is a dress.
_TITLE_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("ski suit", "snowsuit", "snow suit", "one-piece", "snowmobile suit"), "outerwear", "ski suit"),
    (("bib", "bibs", "ski pant", "ski pants", "snow pant", "snow pants", "shell pant", "shell pants",
      "hardshell pant", "hardshell pants", "insulated pant", "insulated pants"),
     "bottoms", "snow pants"),
    (("baselayer bottom", "base layer bottom", "leggings", "tights"), "bottoms", "leggings"),
    (("baselayer", "base layer", "capilene", "thermal"), "tops", "base layer"),
    (("raincoat", "rain jacket", "rainshell", "rain shell"), "outerwear", "raincoat"),
    (("trench",), "outerwear", "coat"),
    (("parka", "overcoat", "peacoat", "pea coat", "topcoat", "coat"), "outerwear", "coat"),
    (("blazer", "sport coat", "suit jacket"), "outerwear", "blazer"),
    (("puffer", "puffy", "down jacket", "down hoody", "down hoodie", "down sweater"), "outerwear", "puffer"),
    (("vest", "gilet"), "outerwear", "vest"),
    (("jacket", "windbreaker", "anorak", "bomber", "shacket", "fleece", "shell", "hardshell", "softshell"),
     "outerwear", "jacket"),
    (("dress", "jumpsuit", "romper"), "dresses", "dress"),
    (("overalls",), "bottoms", "overalls"),
    (("jeans",), "bottoms", "jeans"),
    (("shorts",), "bottoms", "shorts"),
    (("skirt",), "bottoms", "skirt"),
    (("pants", "trousers", "slacks", "chinos", "cargos", "joggers", "sweatpants"), "bottoms", "trousers"),
    (("hoodie", "hoody", "hooded sweatshirt", "pullover hood"), "tops", "hoodie"),
    (("crewneck", "sweatshirt"), "tops", "sweatshirt"),
    (("sweater", "cardigan", "knit pullover", "turtleneck"), "tops", "sweater"),
    (("button up", "button-up", "button down", "button-down", "flannel", "western shirt", "pearl snap"), "tops", "shirt"),
    (("polo",), "tops", "polo"),
    (("blouse",), "tops", "blouse"),
    (("tee", "t-shirt", "t shirt", "tank", "jersey", "ringer"), "tops", "t-shirt"),
    (("1/4 zip", "half zip", "1/2 zip", "quarter zip", "pullover"), "tops", "top"),
    (("boots", "boot", "booties"), "shoes", "boots"),
    (("sneakers", "trainers", "running shoes", "shoes", "slip-ons", "slip ons", "clogs", "loafers"), "shoes", "sneakers"),
    (("purse", "handbag", "tote", "backpack", "crossbody", "clutch"), "bags", "handbag"),
    (("beanie", "toque", "hat", "cap", "snapback", "trucker"), "accessories", "hat"),
    (("glove", "gloves", "mitten", "mittens", "mitt"), "accessories", "gloves"),
    (("scarf", "bandana", "neck gaiter", "buff"), "accessories", "scarf"),
    (("belt",), "accessories", "belt"),
)

# Colors the engine understands (outfit_generator._COLOR_KEYWORDS plus common
# shop wording). Multi-word first.
_COLORS = (
    "off white", "off-white", "powder blue", "light blue", "baby blue", "navy blue", "forest green", "hunter green",
    "olive green", "army green", "tie dye", "tie-dye",
    "navy", "black", "white", "grey", "gray", "charcoal", "silver", "beige", "cream", "ivory", "tan", "khaki",
    "camel", "taupe", "brown", "chocolate", "denim", "burgundy", "maroon", "wine", "crimson", "red", "fuchsia",
    "magenta", "blush", "pink", "rust", "coral", "peach", "orange", "mustard", "gold", "yellow", "olive", "sage",
    "mint", "emerald", "green", "teal", "turquoise", "cobalt", "blue", "lavender", "lilac", "violet", "plum",
    "purple", "plaid", "floral", "striped", "stripe", "camo", "multicolor", "multi",
)
_COLOR_ALIASES = {"tie dye": "multicolor", "tie-dye": "multicolor", "camo": "olive camo", "striped": "stripe"}

_MATERIALS = (
    ("gore-tex", "waterproof gore-tex"), ("goretex", "waterproof gore-tex"), ("cashmere", "cashmere"),
    ("merino", "merino wool"), ("wool", "wool"), ("fleece", "fleece"), ("down", "down"), ("primaloft", "synthetic insulation"),
    ("suede", "suede"), ("leather", "leather"), ("denim", "denim"), ("corduroy", "corduroy"), ("linen", "linen"),
    ("silk", "silk"), ("satin", "satin"), ("velvet", "velvet"), ("nylon", "nylon"), ("polyester", "polyester"),
    ("knit", "knit"), ("flannel", "cotton flannel"), ("cotton", "cotton"),
)
_DOWN = re.compile(r"\b(goose |duck )?down (jacket|vest|filled|fill|puffer|parka|hood|hoody|hoodie|sweater|beanie|insulat\w*)"
                   r"|\b\d{3} ?fill\b|\bdown-filled\b")
_DENIM_SUBS = ("jeans", "overalls")

_SEASONS = {
    ("outerwear", "ski suit"): "winter", ("outerwear", "coat"): "fall, winter", ("outerwear", "puffer"): "fall, winter",
    ("outerwear", "jacket"): "spring, fall", ("outerwear", "raincoat"): "spring, fall", ("outerwear", "vest"): "fall, winter", ("outerwear", "blazer"): "all season",
    ("bottoms", "snow pants"): "winter", ("bottoms", "leggings"): "fall, winter", ("tops", "base layer"): "fall, winter",
    ("tops", "sweatshirt"): "fall, winter", ("tops", "hoodie"): "fall, winter", ("tops", "sweater"): "fall, winter",
    ("tops", "t-shirt"): "spring, summer", ("tops", "blouse"): "spring, summer", ("tops", "polo"): "spring, summer",
    ("bottoms", "shorts"): "spring, summer", ("accessories", "scarf"): "fall, winter",
    ("accessories", "gloves"): "fall, winter", ("shoes", "boots"): "fall, winter",
}
_WARM_SEASON = "fall, winter"
_WARM_WORDS = ("insulated", "beanie", "toque", "winter", "snow", "ski", "sherpa", "thermal")

_FORMALITY = {
    ("outerwear", "blazer"): "business", ("outerwear", "coat"): "smart casual", ("tops", "shirt"): "smart casual",
    ("tops", "blouse"): "smart casual", ("tops", "polo"): "smart casual", ("tops", "sweater"): "smart casual",
    ("bottoms", "skirt"): "smart casual", ("dresses", "dress"): "smart casual", ("bags", "handbag"): "smart casual",
}
_CASUAL_WORDS = ("graphic", "tour", "band", "nfl", "nba", "mlb", "nhl", "ncaa", "college", "logo", "souvenir",
                 "harley", "wrestling", "racing", "nascar", "cartoon", "disney", "rework", "distressed", "fringe",
                 "ski", "snow", "hike", "hiking", "trail", "climbing", "fleece", "puffy", "running")
_FORMAL_WORDS = ("gown", "cocktail", "evening", "formal", "sequin", "prom")

# Waterproof only when the listing says so (brand membranes count). "Soft shell" never does.
_WATERPROOF_WORDS = ("waterproof", "gore-tex", "goretex", "rain jacket", "raincoat", "rain coat", "rain shell",
                     "rainshell", "hardshell", "hard shell", "dryvent", "h2no", "futurelight", "omni-tech",
                     "pertex shield", "event fabric", "winter shell", "insulated shell")
_NOT_WATERPROOF = re.compile(r"\bsoft ?shell\b|\bwater[- ]resistant\b|\bnot waterproof\b")
_WATERPROOF_CATEGORIES = ("outerwear", "shoes", "accessories")

_USED_DESCRIPTION = re.compile(
    r"\b(used|pre-?owned|consign\w*|condition|gently worn|worn|previous use|signs of (wear|use)|lightly used)\b"
)


def _text(*parts: Optional[str]) -> str:
    raw = " ".join(p for p in parts if p)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip().lower()


def _word_in(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def classify(product_type: str, title: str) -> Optional[tuple[str, str]]:
    """(category, subcategory) for a listing, or None when it isn't wearable clothing we score."""
    ptype, t = product_type.strip().lower(), title.lower()
    if any(s in ptype for s in _SKIP_TYPES) or _KID_SIZE.search(t) or any(_word_in(t, w) for w in _GEAR_WORDS):
        return None
    by_type = next(((c, s) for key, c, s in _TYPE_RULES if key in ptype), None)
    if by_type is None and (any(g in ptype for g in _GEAR_TYPES) or any(_word_in(t, w) for w in _SKIP_WORDS)):
        return None
    by_title = [(c, s) for words, c, s in _TITLE_RULES if any(_word_in(t, w) for w in words)]
    if not by_type:
        return by_title[0] if by_title else None
    # The title is more specific than a store's coarse type ("jackets" may be a vest), so use
    # the first title match in the type's family. If the title names only other families, the
    # listing was filed under the wrong type ("Puffy Jacket" under SHOES): trust the title.
    same_family = [k for k in by_title if k[0] == by_type[0]]
    if same_family:
        return same_family[0]
    return by_title[0] if by_title else by_type


def _color(text: str) -> Optional[str]:
    for c in _COLORS:
        if _word_in(text, c):
            return _COLOR_ALIASES.get(c, c)
    return None


def _material(text: str, category: str, subcategory: str) -> Optional[str]:
    for key, name in _MATERIALS:
        if key == "down":
            if _DOWN.search(text):
                return name
        elif _word_in(text, key):
            return name
    if subcategory in _DENIM_SUBS:
        return "denim"
    if (category, subcategory) in (("tops", "t-shirt"), ("tops", "sweatshirt"), ("tops", "hoodie")):
        return "cotton"
    return None


def _formality(text: str, category: str, subcategory: str) -> str:
    if any(_word_in(text, w) for w in _FORMAL_WORDS):
        return "formal"
    if any(_word_in(text, w) for w in _CASUAL_WORDS):
        return "casual"
    return _FORMALITY.get((category, subcategory), "casual")


def _season(title: str, category: str, subcategory: str, material: Optional[str]) -> str:
    if material and any(w in material for w in ("wool", "cashmere", "fleece", "down", "corduroy", "insulation")):
        return _WARM_SEASON
    if material == "linen":
        return "spring, summer"
    season = _SEASONS.get((category, subcategory))
    if season:
        return season
    if any(_word_in(title, w) for w in _WARM_WORDS):
        return _WARM_SEASON
    return "all season"


def _image(product: dict[str, Any]) -> Optional[str]:
    images = product.get("images") or []
    if not images or not images[0].get("src"):
        return None
    src = images[0]["src"]
    return f"{src}{'&' if '?' in src else '?'}width={IMAGE_WIDTH}"


def _name(title: str) -> str:
    """Store titles run long ("... Womens L"); keep them readable on a card."""
    name = re.sub(r"\s+", " ", html.unescape(title)).strip()
    return name if len(name) <= 70 else name[:67].rsplit(" ", 1)[0] + "…"


def _options(product: dict[str, Any], variant: dict[str, Any]) -> dict[str, str]:
    """A variant's option values by option name: {"size": "L", "color": "Black/White", "condition": "Used"}."""
    names = [str(o.get("name") or "").strip().lower() for o in product.get("options") or []]
    values = [variant.get(f"option{i}") for i in (1, 2, 3)]
    return {n: str(v) for n, v in zip(names, values) if n and v}


def _is_used(variant_options: dict[str, str], variant: dict[str, Any]) -> bool:
    condition = variant_options.get("condition") or variant.get("title") or ""
    return re.search(r"\bused\b", condition.lower()) is not None


def normalize(store: Store, product: dict[str, Any]) -> Optional[dict[str, Any]]:
    """One Shopify listing as a catalog entry, or None (sold out, new stock, not clothing, no price)."""
    title = product.get("title") or ""
    kind = classify(product.get("product_type") or "", title)
    if kind is None:
        return None
    available = [(v, _options(product, v)) for v in product.get("variants") or [] if v.get("available")]
    if store.condition == "used_variant":
        available = [(v, o) for v, o in available if _is_used(o, v)]
    elif store.condition == "described_used" and not _USED_DESCRIPTION.search(_text(product.get("body_html"))):
        return None
    if not available:
        return None
    try:
        price = min(float(v["price"]) for v, _ in available)
    except (KeyError, TypeError, ValueError):
        return None
    if price <= 0:
        return None
    category, subcategory = kind
    tags = [str(t) for t in product.get("tags") or []]
    option_colors = " ".join(o.get("color", "") for _, o in available).lower()
    # Color: title first (it names the piece's main color), then the variant's color option,
    # then tags, then the description.
    color = (_color(title.lower()) or _color(option_colors) or _color(" ".join(tags).lower())
             or _color(_text(product.get("body_html"))))
    blob = _text(title, product.get("product_type"), " ".join(tags), product.get("body_html"))
    # Material: the title and tags name the fabric; descriptions mention linings and trims, so
    # they're only a fallback.
    material = _material(_text(title, " ".join(tags)), category, subcategory) or _material(blob, category, subcategory)
    waterproof = (category in _WATERPROOF_CATEGORIES and not _NOT_WATERPROOF.search(_text(title))
                  and any(_word_in(blob, w) for w in _WATERPROOF_WORDS))
    sizes: list[str] = []
    for v, o in available:
        size = o.get("size") or (v.get("title") if len(o) <= 1 else None)
        if size and size != "Default Title" and size not in sizes:
            sizes.append(size)
    price_out: float | int = int(price) if price.is_integer() else round(price, 2)
    return {
        "id": f"{store.key}_{product['id']}",
        "name": _name(title),
        "store": store.name,
        "store_location": store.location,
        "price": price_out,
        "image": _image(product),
        "url": f"https://{store.domain}/products/{product.get('handle')}",
        "category": category,
        "subcategory": subcategory,
        "color": color,
        "style": store.style,
        "formality": _formality(_text(title, product.get("product_type"), " ".join(tags)), category, subcategory),
        "season": _season(title.lower(), category, subcategory, material),
        "material": material,
        "waterproof": waterproof,
        "sizes": sizes,
        "sponsored": False,
        "secondhand": True,
        "updated_at": product.get("updated_at"),
    }


def build_catalog(raw_by_store: Iterable[tuple[Store, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    entries = [e for store, raw in raw_by_store for p in raw if (e := normalize(store, p))]
    return sorted(entries, key=lambda e: e["id"])
