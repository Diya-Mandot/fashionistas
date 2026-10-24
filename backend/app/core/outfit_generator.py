"""
app/core/outfit_generator.py
----------------------------
Deterministic, rules-based outfit generation.

Pure functions only: no database, network, or global random state. The
router converts ORM rows into `ItemData` and passes them in, which keeps
every rule here unit-testable with plain in-memory objects.

Pipeline
    filter_for_weather -> generate_candidates (templates + scoring)
    -> diversify -> (LLM curation happens in app/core/outfit_curator.py)

Templates
    top + bottom + shoes          (activewear may fill top and/or bottom)
    dress + shoes
    + optional outerwear          (strongly preferred when cold or wet)
    + at most one accessory-or-bag
    Shoe-less combos are allowed only when the closet has no eligible
    shoes, and carry a score penalty. Every combo has 2-6 items.
"""

from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Sequence

# ---------------------------------------------------------------------------
# Tunables (named so the scoring is explainable and adjustable)
# ---------------------------------------------------------------------------
W_COLOR = 0.30
W_STYLE = 0.25
W_WEATHER = 0.20
W_ROTATION = 0.15
W_FAVORITE = 0.05
W_JITTER = 0.02                 # tie-breaker only; must stay below meaningful signal gaps

SHOELESS_PENALTY = 0.25
REUSE_PENALTY = 0.15            # per already-selected use of an item, during diversify

COLD_F = 55                     # below this, outerwear is strongly preferred
HOT_F = 80                      # at/above this, outerwear is dropped unless wet
VERY_COLD_F = 45                # below this, summer-only pieces are filtered out

MAX_PER_SLOT = 12               # best items per slot before combining
MAX_LAYER_OPTIONS = 4           # best outerwear / extras considered per base combo
MAX_BASE_COMBOS = 60            # best base combos expanded with layers/extras
DEFAULT_CANDIDATES = 20
MIN_ITEMS = 2
MAX_ITEMS = 6

DEFAULT_STYLE = "casual"

# Style tags the app no longer offers, mapped to the closest current style.
# Items saved before the change still carry these.
_LEGACY_STYLES = {"business": "smart casual", "trendy": "streetwear"}

# Styles considered appropriate per occasion (lowercase). Empty set = all styles allowed.
OCCASION_STYLES: dict[str, set[str]] = {
    "work": {"formal", "smart casual"},
    "gym": {"sporty"},
    "going out": {"smart casual", "streetwear", "bohemian", "vintage", "casual", "formal"},
    "date night": {"smart casual", "formal", "bohemian", "vintage"},
    "casual": set(),  # all styles
}


def eligible_styles(occasion: str) -> set[str]:
    """Return style tags compatible with this occasion. Empty set means no restriction."""
    return OCCASION_STYLES.get((occasion or "").strip().lower(), set())


def parse_styles_override(styles: Optional[str], max_entries: int = 20) -> set[str]:
    """Parse a comma-separated style override ("Casual,Sporty") into lowercase tags."""
    if not styles:
        return set()
    parsed = [s.strip().lower()[:40] for s in styles.split(",") if s.strip()]
    return {_LEGACY_STYLES.get(s, s) for s in parsed[:max_entries]}


def stored_style_tags(allowed: set[str]) -> set[str]:
    """Allowed styles plus the retired tags that map onto them.

    Use this when filtering raw stored style values, which may still be
    retired tags.
    """
    return allowed | {old for old, new in _LEGACY_STYLES.items() if new in allowed}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ItemData:
    """Plain projection of a wardrobe item used by the generator."""

    id: str
    category: str
    name: Optional[str] = None
    subcategory: Optional[str] = None
    color: Optional[str] = None
    style: Optional[str] = None
    season: Optional[str] = None
    last_worn: Optional[date] = None
    times_worn: int = 0
    is_favorite: bool = False


@dataclass(frozen=True)
class WeatherContext:
    """Today's weather as the client reported it.

    Both fields are optional. With no temperature, the weather rules are
    skipped entirely, so suggestions still work when the client has no
    location or the weather lookup failed.
    """

    temp_f: Optional[int] = None
    precipitation: bool = False

    @property
    def is_cold(self) -> bool:
        return self.temp_f is not None and self.temp_f < COLD_F

    @property
    def is_hot(self) -> bool:
        return self.temp_f is not None and self.temp_f >= HOT_F

    @property
    def wants_outerwear(self) -> bool:
        return self.is_cold or self.precipitation


@dataclass(frozen=True)
class Candidate:
    """One scored outfit.

    `key` ignores item order, so it is what we compare when skipping saved
    outfits and duplicate combos.
    """

    items: tuple  # tuple[ItemData, ...] in display order
    score: float
    shoeless: bool = False

    @property
    def item_ids(self) -> list[str]:
        return [i.id for i in self.items]

    @property
    def key(self) -> frozenset:
        return frozenset(self.item_ids)


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------
SLOT_ORDER = {"top": 0, "bottom": 1, "dress": 2, "outerwear": 3, "shoes": 4, "extra": 5}

_ACTIVE_BOTTOM_WORDS = ("legging", "short", "pant", "jogger", "skirt", "tight", "sweatpant", "bottom")
_ACTIVE_TOP_WORDS = ("bra", "tank", "tee", "t-shirt", "shirt", "top", "hoodie", "sweatshirt", "jersey", "pullover")


def _activewear_slots(item: ItemData) -> set[str]:
    """Best-effort guess of which slot(s) an activewear piece can fill."""
    text = f"{item.subcategory or ''} {item.name or ''}".lower()
    is_bottom = any(w in text for w in _ACTIVE_BOTTOM_WORDS)
    is_top = any(w in text for w in _ACTIVE_TOP_WORDS)
    if is_bottom and not is_top:
        return {"bottom"}
    if is_top and not is_bottom:
        return {"top"}
    return {"top", "bottom"}


def item_slots(item: ItemData) -> set[str]:
    """Which outfit slot(s) an item can fill.

    Unknown categories return an empty set, so those items are simply never
    used rather than causing an error.
    """
    category = (item.category or "").lower()
    if category == "tops":
        return {"top"}
    if category == "bottoms":
        return {"bottom"}
    if category == "dresses":
        return {"dress"}
    if category == "shoes":
        return {"shoes"}
    if category == "outerwear":
        return {"outerwear"}
    if category in ("accessories", "bags"):
        return {"extra"}
    if category == "activewear":
        return _activewear_slots(item)
    return set()


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
NEUTRAL = "neutral"
MULTI = "multi"

# Checked in order: more specific keywords first so "navy blue" -> neutral,
# "off-white" -> neutral, "light blue" -> blue.
_COLOR_KEYWORDS: list[tuple[str, str]] = [
    ("navy", NEUTRAL), ("denim", NEUTRAL), ("off-white", NEUTRAL), ("off white", NEUTRAL),
    ("black", NEUTRAL), ("white", NEUTRAL), ("grey", NEUTRAL), ("gray", NEUTRAL),
    ("charcoal", NEUTRAL), ("silver", NEUTRAL), ("beige", NEUTRAL), ("cream", NEUTRAL),
    ("ivory", NEUTRAL), ("tan", NEUTRAL), ("khaki", NEUTRAL), ("camel", NEUTRAL),
    ("taupe", NEUTRAL), ("nude", NEUTRAL), ("brown", NEUTRAL), ("chocolate", NEUTRAL),
    ("multi", MULTI), ("print", MULTI), ("floral", MULTI), ("pattern", MULTI),
    ("stripe", MULTI), ("plaid", MULTI), ("check", MULTI), ("rainbow", MULTI),
    ("burgundy", "red"), ("maroon", "red"), ("wine", "red"), ("crimson", "red"), ("red", "red"),
    ("fuchsia", "pink"), ("magenta", "pink"), ("blush", "pink"), ("rose", "pink"), ("pink", "pink"),
    ("rust", "orange"), ("coral", "orange"), ("peach", "orange"), ("terracotta", "orange"),
    ("orange", "orange"),
    ("mustard", "yellow"), ("gold", "yellow"), ("yellow", "yellow"),
    ("olive", "green"), ("sage", "green"), ("mint", "green"), ("emerald", "green"),
    ("green", "green"),
    ("teal", "blue"), ("turquoise", "blue"), ("cobalt", "blue"), ("blue", "blue"),
    ("lavender", "purple"), ("lilac", "purple"), ("violet", "purple"), ("plum", "purple"),
    ("purple", "purple"),
]

_HARMONIOUS_PAIRS = {
    frozenset(p) for p in [
        # analogous
        ("red", "orange"), ("orange", "yellow"), ("yellow", "green"), ("green", "blue"),
        ("blue", "purple"), ("purple", "pink"), ("pink", "red"),
        # complementary-ish pairings that read well in clothing
        ("blue", "orange"), ("purple", "yellow"), ("pink", "green"), ("blue", "yellow"),
        ("blue", "pink"),
    ]
}


def color_family(color: Optional[str]) -> str:
    """Normalize free-text color into a family. Unknown -> neutral."""
    if not color:
        return NEUTRAL
    text = color.strip().lower()
    for keyword, family in _COLOR_KEYWORDS:
        if keyword in text:
            return family
    return NEUTRAL


def color_harmony(items: Sequence[ItemData]) -> float:
    """Score in [-1, 1]. Neutrals pair with anything; >2 strong accents is penalized."""
    accents = {color_family(i.color) for i in items} - {NEUTRAL}
    if not accents:
        return 0.7
    if len(accents) == 1:
        return 1.0
    if len(accents) == 2:
        if MULTI in accents:
            return 0.0
        return 0.6 if frozenset(accents) in _HARMONIOUS_PAIRS else 0.2
    return -1.0


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
_COMPATIBLE_STYLES = {
    frozenset(p) for p in [
        ("formal", "smart casual"), ("smart casual", "casual"), ("casual", "streetwear"),
        ("casual", "sporty"), ("streetwear", "sporty"), ("bohemian", "vintage"),
        ("casual", "bohemian"), ("casual", "vintage"), ("streetwear", "vintage"),
        ("smart casual", "vintage"),
    ]
}


def normalize_style(style: Optional[str]) -> str:
    """Lowercase a style tag, treat blank as casual, and map retired tags."""
    normalized = (style or DEFAULT_STYLE).strip().lower() or DEFAULT_STYLE
    return _LEGACY_STYLES.get(normalized, normalized)


def style_coherence(items: Sequence[ItemData]) -> float:
    """Score in [-1, 1]. One style -> 1; compatible pairs -> 0.5; clashing pairs -> -1."""
    styles = sorted({normalize_style(i.style) for i in items})
    if len(styles) <= 1:
        return 1.0
    pair_scores = [
        0.5 if frozenset((a, b)) in _COMPATIBLE_STYLES else -1.0
        for a, b in itertools.combinations(styles, 2)
    ]
    return sum(pair_scores) / len(pair_scores)


def dominant_style(items: Sequence[ItemData]) -> str:
    """Most common style in the outfit; ties go to the alphabetically first."""
    counts: dict[str, int] = {}
    for item in items:
        s = normalize_style(item.style)
        counts[s] = counts.get(s, 0) + 1
    return max(sorted(counts), key=lambda s: counts[s]) if counts else DEFAULT_STYLE


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
_SEASON_WORDS = {
    "winter": "winter", "fall": "fall", "autumn": "fall", "spring": "spring", "summer": "summer",
}
_ALL_SEASON_WORDS = ("all", "any", "year", "every")


def parse_seasons(season: Optional[str]) -> Optional[set[str]]:
    """Return set of seasons, {'all'} for all-season, or None when unknown."""
    if not season:
        return None
    text = season.strip().lower()
    if any(re.search(rf"\b{w}\b", text) for w in _ALL_SEASON_WORDS):
        return {"all"}
    found = {canon for word, canon in _SEASON_WORDS.items() if re.search(rf"\b{word}\b", text)}
    return found or None


def _target_seasons(weather: WeatherContext) -> Optional[set[str]]:
    """Seasons that suit today's temperature. Mild days count as spring or fall."""
    if weather.temp_f is None:
        return None
    if weather.is_cold:
        return {"winter", "fall"}
    if weather.is_hot:
        return {"summer", "spring"}
    return {"spring", "fall"}


def weather_allows(item: ItemData, weather: WeatherContext) -> bool:
    """Hard filter. Lenient: only removes clear mismatches; unknown season passes."""
    if weather.temp_f is None:
        return True
    is_outerwear = (item.category or "").lower() == "outerwear"
    if is_outerwear and weather.is_hot:
        # Hot and dry: no layers. Hot and wet: any outerwear can serve as a rain layer.
        return weather.precipitation
    seasons = parse_seasons(item.season)
    if not seasons or "all" in seasons:
        return True
    if weather.temp_f < VERY_COLD_F and seasons <= {"summer"}:
        return False
    if weather.is_hot and seasons <= {"winter"}:
        return False
    return True


def filter_for_weather(items: Iterable[ItemData], weather: WeatherContext) -> list[ItemData]:
    return [i for i in items if weather_allows(i, weather)]


def item_weather_fit(item: ItemData, weather: WeatherContext) -> float:
    """Soft score in [-1, 1] used for ranking."""
    target = _target_seasons(weather)
    if target is None:
        return 0.0
    seasons = parse_seasons(item.season)
    if seasons is None:
        return 0.0
    if "all" in seasons:
        return 0.5
    return 1.0 if seasons & target else -1.0


def combo_weather_fit(items: Sequence[ItemData], weather: WeatherContext) -> float:
    """Score in [-1, 1]: average item fit, adjusted for having (or missing) a layer."""
    if weather.temp_f is None and not weather.precipitation:
        return 0.0
    base = sum(item_weather_fit(i, weather) for i in items) / len(items)
    has_outer = any("outerwear" in item_slots(i) for i in items)
    if weather.wants_outerwear:
        base += 1.0 if has_outer else -1.0
    elif weather.is_hot and has_outer:
        base -= 0.5
    return max(-1.0, min(1.0, base))


# ---------------------------------------------------------------------------
# Rotation / favorites
# ---------------------------------------------------------------------------
def item_rotation(item: ItemData, today: date) -> float:
    """Score in [0, 1]. Rarely or not-recently worn items score higher.

    Recency reaches its max once an item hasn't been worn for 30 days.
    Frequency halves at 5 wears, so heavy favourites still show up, just less.
    """
    if item.last_worn is None:
        recency = 1.0
    else:
        days = max(0, (today - item.last_worn).days)
        recency = min(1.0, days / 30.0)
    frequency = 1.0 / (1.0 + max(0, item.times_worn) / 5.0)
    return 0.6 * recency + 0.4 * frequency


def _item_rank_score(item: ItemData, weather: WeatherContext, today: date, rng: random.Random) -> float:
    """Per-item score used only to trim each slot before combining.

    Colour and style are left out because they only mean something for a
    whole outfit.
    """
    return (
        W_WEATHER * item_weather_fit(item, weather)
        + W_ROTATION * item_rotation(item, today)
        + W_FAVORITE * (1.0 if item.is_favorite else 0.0)
        + W_JITTER * rng.random()
    )


def score_combo(
    items: Sequence[ItemData],
    weather: WeatherContext,
    today: date,
    rng: random.Random,
    shoeless: bool = False,
) -> float:
    """Weighted sum of the outfit signals; higher is better.

    The weights add up to just under 1, so a near-perfect outfit scores
    about 0.97 before any shoeless penalty.
    """
    rotation = sum(item_rotation(i, today) for i in items) / len(items)
    favorite = sum(1 for i in items if i.is_favorite) / len(items)
    score = (
        W_COLOR * color_harmony(items)
        + W_STYLE * style_coherence(items)
        + W_WEATHER * combo_weather_fit(items, weather)
        + W_ROTATION * rotation
        + W_FAVORITE * favorite
        + W_JITTER * rng.random()
    )
    if shoeless:
        score -= SHOELESS_PENALTY
    return score


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _order_items(assigned: Sequence[tuple[str, ItemData]]) -> tuple:
    """Sort an outfit top-to-bottom (see SLOT_ORDER) for display."""
    return tuple(item for _slot, item in sorted(assigned, key=lambda p: SLOT_ORDER[p[0]]))


def generate_candidates(
    items: Iterable[ItemData],
    weather: Optional[WeatherContext] = None,
    *,
    today: date,
    seed: Optional[int] = None,
    exclude: Iterable[frozenset] = (),
) -> list[Candidate]:
    """Build every valid templated combo (bounded) and return them ranked by score.

    The search is capped so a large closet stays fast. Each slot keeps only its
    best items, at most MAX_BASE_COMBOS base outfits are expanded, and each
    of those tries a few layers and extras. That caps the output at about
    1,500 candidates however big the closet is.

    The same seed and closet always give the same result.
    """
    weather = weather or WeatherContext()
    rng = random.Random(seed)
    excluded = {frozenset(e) for e in exclude}

    # Deduplicate by id and sort for deterministic iteration regardless of input order.
    unique: dict[str, ItemData] = {}
    for item in items:
        unique.setdefault(item.id, item)
    pool = [unique[k] for k in sorted(unique)]

    slots: dict[str, list[ItemData]] = {s: [] for s in SLOT_ORDER}
    for item in pool:
        for slot in sorted(item_slots(item)):
            slots[slot].append(item)

    # Keep only the strongest items per slot. Ties break on id so the cut is stable.
    rank = {item.id: _item_rank_score(item, weather, today, rng) for item in pool}
    for slot, members in slots.items():
        members.sort(key=lambda i: (-rank[i.id], i.id))
        limit = MAX_LAYER_OPTIONS if slot in ("outerwear", "extra") else MAX_PER_SLOT
        del members[limit:]

    # With no shoes at all, use None as a placeholder shoe so combos can still form.
    shoeless = not slots["shoes"]
    shoe_options: list[Optional[ItemData]] = list(slots["shoes"]) if not shoeless else [None]

    # Stage 1: base combos (top + bottom + shoes, or dress + shoes).
    bases: list[tuple[float, list[tuple[str, ItemData]]]] = []
    for top, bottom, shoe in itertools.product(slots["top"], slots["bottom"], shoe_options):
        if top.id == bottom.id:  # one activewear piece cannot fill both slots
            continue
        assigned = [("top", top), ("bottom", bottom)]
        if shoe is not None:
            assigned.append(("shoes", shoe))
        bases.append((score_combo([i for _, i in assigned], weather, today, rng, shoeless), assigned))
    for dress, shoe in itertools.product(slots["dress"], shoe_options):
        assigned = [("dress", dress)]
        if shoe is not None:
            assigned.append(("shoes", shoe))
        bases.append((score_combo([i for _, i in assigned], weather, today, rng, shoeless), assigned))

    bases.sort(key=lambda b: (-b[0], tuple(i.id for _, i in b[1])))
    bases = bases[:MAX_BASE_COMBOS]

    # Stage 2: optional outerwear + optional single extra. None means "skip this
    # slot", so the bare base outfit is always tried too.
    outer_options: list[Optional[ItemData]] = [None] + slots["outerwear"]
    extra_options: list[Optional[ItemData]] = [None] + slots["extra"]
    seen: set[frozenset] = set()
    candidates: list[Candidate] = []
    for _base_score, base in bases:
        base_ids = {i.id for _, i in base}
        for outer, extra in itertools.product(outer_options, extra_options):
            assigned = list(base)
            if outer is not None:
                if outer.id in base_ids:
                    continue
                assigned.append(("outerwear", outer))
            if extra is not None:
                assigned.append(("extra", extra))
            if not (MIN_ITEMS <= len(assigned) <= MAX_ITEMS):
                continue
            ordered = _order_items(assigned)
            # Skip combos that reuse an item, were already built, or are excluded (e.g. saved).
            key = frozenset(i.id for i in ordered)
            if len(key) != len(ordered) or key in seen or key in excluded:
                continue
            seen.add(key)
            score = score_combo(ordered, weather, today, rng, shoeless)
            candidates.append(Candidate(items=ordered, score=round(score, 4), shoeless=shoeless))

    candidates.sort(key=lambda c: (-c.score, tuple(c.item_ids)))
    return candidates


def diversify(candidates: Sequence[Candidate], k: int = DEFAULT_CANDIDATES) -> list[Candidate]:
    """Greedy selection that penalizes reusing the same item across picks."""
    remaining = list(candidates)
    usage: dict[str, int] = {}
    picked: list[Candidate] = []
    while remaining and len(picked) < k:
        best_idx = 0
        best_val = float("-inf")
        for idx, cand in enumerate(remaining):
            val = cand.score - REUSE_PENALTY * sum(usage.get(i, 0) for i in cand.item_ids)
            if val > best_val:
                best_val, best_idx = val, idx
        chosen = remaining.pop(best_idx)
        picked.append(chosen)
        for item_id in chosen.item_ids:
            usage[item_id] = usage.get(item_id, 0) + 1
    return picked


# ---------------------------------------------------------------------------
# Template copy (used when the LLM is unavailable or returns too few picks)
# ---------------------------------------------------------------------------
VIBE_MAX = 40
TIP_MAX = 200

_STYLE_VIBES = {
    "formal": "Sharp & Polished",
    "smart casual": "Smart Casual Edge",
    "casual": "Easy Everyday",
    "streetwear": "Street Ready",
    "sporty": "Active Mode",
    "bohemian": "Boho Breeze",
    "vintage": "Vintage Revival",
}


_CATEGORY_NOUNS = {
    "tops": "top",
    "bottoms": "bottoms",
    "outerwear": "jacket",
    "dresses": "dress",
    "shoes": "shoes",
    "accessories": "accessory",
    "activewear": "activewear",
    "bags": "bag",
}


def _short_name(item: ItemData, max_len: int = 40) -> str:
    """Name to use in a tip: the item's name, else its subcategory, else a noun.

    Control characters are stripped because names are user-entered text.
    """
    subcategory = (item.subcategory or "").strip()
    if subcategory.lower() == "other":
        subcategory = ""
    name = (item.name or "").strip() or subcategory or _CATEGORY_NOUNS.get(item.category, "piece")
    name = re.sub(r"[\x00-\x1f\x7f]", " ", name)
    return name[:max_len].strip()


def template_copy(candidate: Candidate, weather: Optional[WeatherContext], today: date) -> tuple[str, str]:
    """Deterministic (vibe, tip) for a rules-ranked candidate."""
    weather = weather or WeatherContext()
    items = candidate.items
    vibe = _STYLE_VIBES.get(dominant_style(items), "Your Look")
    outer = next((i for i in items if "outerwear" in item_slots(i)), None)
    accents = sorted({color_family(i.color) for i in items} - {NEUTRAL, MULTI})
    unworn = next((i for i in items if i.last_worn is None and i.times_worn == 0), None)

    # Most useful tip first: weather, then never-worn items, then colour notes.
    if outer is not None and weather.precipitation:
        tip = f"The {_short_name(outer)} keeps you covered if it rains."
    elif outer is not None and weather.is_cold:
        tip = f"Layer the {_short_name(outer)} on top to stay warm."
    elif unworn is not None:
        tip = f"A great chance to give your {_short_name(unworn)} its first wear."
    elif len(accents) == 1:
        tip = f"The {accents[0]} accent pops against the rest of the look."
    elif not accents:
        tip = "A neutral palette keeps this look easy and put-together."
    else:
        tip = "Coordinated colors tie the pieces together."
    return vibe[:VIBE_MAX], tip[:TIP_MAX]


# ---------------------------------------------------------------------------
# Legacy exclude parsing
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")


def parse_exclude(exclude: Optional[str], max_combos: int = 50) -> list[frozenset]:
    """Parse legacy "id,id|id,id" combos. Malformed parts are ignored.

    IDs are normalised to lowercase dashed form so they match ItemData ids.
    Combos with fewer than two valid ids can't be a real outfit and are dropped.
    """
    if not exclude:
        return []
    combos: list[frozenset] = []
    for combo_str in exclude.split("|")[:max_combos]:
        ids = set()
        for raw in combo_str.split(","):
            raw = raw.strip()
            if not raw or not _UUID_RE.match(raw):
                continue
            hex_ = raw.replace("-", "").lower()
            ids.add(f"{hex_[:8]}-{hex_[8:12]}-{hex_[12:16]}-{hex_[16:20]}-{hex_[20:]}")
        if len(ids) >= MIN_ITEMS:
            combos.append(frozenset(ids))
    return combos
