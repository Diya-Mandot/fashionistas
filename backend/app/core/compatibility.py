"""
app/core/compatibility.py
-------------------------
How well a new piece fits a closet: the deterministic half of
Should I Buy This? and the whole of Shop Your Gaps scoring.

Pure functions only, like outfit_generator: no database or network. Callers
convert ORM rows, catalog entries or scan results with `as_piece()`.

Code decides everything countable here (outfits, duplicate candidates, gaps,
calendar matches, a baseline score). Claude only adjusts the result later,
in decisions_client.judge_purchase.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Optional, Sequence

from app.core import outfit_generator as gen
from app.integrations.decisions_client import _dress_target
from app.text_rules import is_athletic

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
FORMALITY_RANK = {"casual": 0, "smart casual": 1, "business": 2, "formal": 3}
MAX_FORMALITY_SPREAD = 1        # base pieces (top, bottom, dress, shoes) within one step of each other
MAX_LAYER_SPREAD = 2            # a coat or accessory may sit up to two steps from the base pieces
MIN_STYLE_COHERENCE = 0.5       # every pair of styles compatible (see gen.style_coherence)
EVENT_FORMALITY_TOLERANCE = 1.5  # |item rank - event target| allowed for a calendar match
CALENDAR_WINDOW_DAYS = 30
TOP_CANDIDATES = 10
OUTFIT_DISPLAY_CAP = 50

BASE_SCORE = 20
PER_OUTFIT, OUTFIT_CAP = 3, 40
GAP_BONUS = 25
PER_EVENT, EVENT_CAP = 5, 15
PER_DUPLICATE, DUPLICATE_CAP = 20, 40

GREAT_BUY_MIN = 70
MAYBE_MIN = 40

CORE_CATEGORIES = ("tops", "bottoms", "outerwear", "shoes")
WARM_MATERIALS = ("wool", "cashmere", "down", "fleece")  # same list as tools/gaps.py


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Piece:
    """One garment, from the closet, the catalog or a scan."""

    id: str
    category: str
    name: str = ""
    subcategory: str = "other"
    color: Optional[str] = None
    style: Optional[str] = None
    formality: str = "casual"
    season: Optional[str] = None
    material: Optional[str] = None
    waterproof: bool = False
    last_worn: Optional[date] = None
    times_worn: int = 0
    is_favorite: bool = False

    def item_data(self) -> gen.ItemData:
        return gen.ItemData(
            id=self.id, category=self.category, name=self.name, subcategory=self.subcategory,
            color=self.color, style=self.style, season=self.season, last_worn=self.last_worn,
            times_worn=self.times_worn, is_favorite=self.is_favorite,
        )


def as_piece(obj: Any) -> Piece:
    """Build a Piece from a WardrobeItem, a catalog dict, or any object/dict with those fields."""
    get = obj.get if isinstance(obj, dict) else lambda k, d=None: getattr(obj, k, d)
    return Piece(
        id=str(get("id") or "new"),
        category=(get("category") or "").lower(),
        name=get("name") or "",
        subcategory=(get("subcategory") or "other").lower(),
        color=get("color"),
        style=get("style"),
        formality=(get("formality") or "casual").lower(),
        season=get("season"),
        material=get("material"),
        waterproof=bool(get("waterproof")),
        last_worn=get("last_worn"),
        times_worn=int(get("number_of_times_worn", get("times_worn", 0)) or 0),
        is_favorite=bool(get("is_favorite")),
    )


@dataclass(frozen=True)
class Outfit:
    items: tuple  # tuple[Piece, ...], top-to-bottom
    score: float


@dataclass(frozen=True)
class Duplicate:
    item: Piece
    reason: str


@dataclass(frozen=True)
class Gap:
    label: str
    category: str
    count: int                  # closet items already in this slot
    want: int = 1               # below this the slot is a gap
    matches: Callable[[Piece], bool] = field(default=lambda p: False, compare=False, repr=False)

    @property
    def status(self) -> str:
        return "empty" if self.count == 0 else "thin"


@dataclass(frozen=True)
class Assessment:
    outfit_count: int
    candidates: list[Outfit]
    duplicates: list[Duplicate]
    gaps_filled: list[str]
    calendar_matches: list[dict[str, str]]
    score: int
    verdict: str


# ---------------------------------------------------------------------------
# Shared attribute helpers
# ---------------------------------------------------------------------------
# Neutral shades, checked in order. color_family() lumps every neutral
# together, which is right for harmony but too coarse for "you already own one".
_NEUTRAL_SHADES = [
    ("off-white", "white"), ("off white", "white"), ("ivory", "white"), ("cream", "white"), ("white", "white"),
    ("navy", "navy"), ("charcoal", "charcoal"), ("black", "black"),
    ("grey", "grey"), ("gray", "grey"), ("heather", "grey"), ("silver", "grey"),
    ("beige", "beige"), ("tan", "beige"), ("khaki", "beige"), ("camel", "beige"), ("taupe", "beige"),
    ("nude", "beige"), ("stone", "beige"), ("oatmeal", "beige"), ("sand", "beige"),
    ("brown", "brown"), ("chocolate", "brown"), ("cognac", "brown"), ("denim", "denim"),
]
DARK_SHADES = {"black", "navy", "charcoal", "grey"}

_SUBCATEGORY_ALIASES = {
    "tee": "t-shirt", "t shirt": "t-shirt", "tshirt": "t-shirt",
    "pants": "trousers", "slacks": "trousers",
    "sneaker": "sneakers", "trainers": "sneakers", "boot": "boots", "heel": "heels", "pumps": "heels",
    "bomber": "jacket", "moto": "jacket", "biker": "jacket", "puffer": "jacket",
}


def color_shade(color: Optional[str]) -> str:
    """A finer color key than color_family: neutrals split into black, navy, beige, and so on."""
    family = gen.color_family(color)
    if family != gen.NEUTRAL:
        return family
    text = (color or "").strip().lower()
    for keyword, shade in _NEUTRAL_SHADES:
        if keyword in text:
            return shade
    return text or gen.NEUTRAL


def silhouette(piece: Piece) -> str:
    sub = (piece.subcategory or "other").strip().lower()
    return _SUBCATEGORY_ALIASES.get(sub, sub)


def formality_rank(piece: Piece) -> int:
    return FORMALITY_RANK.get(piece.formality, 0)


def _slots(piece: Piece) -> set[str]:
    slots = gen.item_slots(piece.item_data())
    # An activewear piece the generator can't place (e.g. a track jacket) counts as a top only.
    return {"top"} if slots == {"top", "bottom"} else slots


def _seasons_overlap(pieces: Sequence[Piece]) -> bool:
    common: Optional[set[str]] = None
    for p in pieces:
        s = gen.parse_seasons(p.season)
        if not s or "all" in s:
            continue  # unknown or all-season pairs with anything
        common = s if common is None else common & s
        if not common:
            return False
    return True


def _season_of(d: date) -> str:
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(d.month, "fall")


# ---------------------------------------------------------------------------
# Outfits
# ---------------------------------------------------------------------------
_LAYER_CATEGORIES = ("outerwear", "accessories", "bags")


def outfit_ok(pieces: Sequence[Piece]) -> bool:
    """The rules a combination must pass to count as a real outfit.

    A dress coat over a turtleneck and jeans is normal, so layers get a wider
    formality allowance than the clothes underneath.
    """
    base = [formality_rank(p) for p in pieces if p.category not in _LAYER_CATEGORIES]
    layers = [formality_rank(p) for p in pieces if p.category in _LAYER_CATEGORIES]
    if base and max(base) - min(base) > MAX_FORMALITY_SPREAD:
        return False
    if base and any(abs(r - b) > MAX_LAYER_SPREAD for r in layers for b in base):
        return False
    if not _seasons_overlap(pieces):
        return False
    data = [p.item_data() for p in pieces]
    return gen.color_harmony(data) >= 0 and gen.style_coherence(data) >= MIN_STYLE_COHERENCE


def _combos_with(new: Piece, closet: Sequence[Piece]) -> Iterable[list[tuple[str, Piece]]]:
    """Every templated outfit in which `new` fills a slot (before the outfit_ok rules)."""
    by_slot: dict[str, list[Piece]] = {s: [] for s in gen.SLOT_ORDER}
    for p in closet:
        for s in _slots(p):
            by_slot[s].append(p)
    shoes: list[Optional[Piece]] = list(by_slot["shoes"]) or [None]  # a shoe-less closet still gets outfits

    def bases(top=None, bottom=None, dress=None, shoe=None):
        tops = [top] if top else by_slot["top"]
        bottoms = [bottom] if bottom else by_slot["bottom"]
        shoe_opts = [shoe] if shoe else shoes
        for t, b, s in itertools.product(tops, bottoms, shoe_opts):
            if t.id != b.id:
                yield [("top", t), ("bottom", b)] + ([("shoes", s)] if s else [])
        if top is None and bottom is None:
            dresses = [dress] if dress else by_slot["dress"]
            for d, s in itertools.product(dresses, shoe_opts):
                yield [("dress", d)] + ([("shoes", s)] if s else [])

    for slot in sorted(_slots(new)):
        if slot == "top":
            yield from bases(top=new)
        elif slot == "bottom":
            yield from bases(bottom=new)
        elif slot == "dress":
            yield from bases(dress=new)
        elif slot == "shoes":
            for base in bases(shoe=new):
                yield base
        elif slot in ("outerwear", "extra"):
            for base in bases():
                yield base + [(slot, new)]


def count_outfits(new: Piece, closet: Sequence[Piece], today: Optional[date] = None) -> tuple[int, list[Outfit]]:
    """How many distinct outfits `new` takes part in, plus the best few for display.

    Outfits are the generator's base templates (top + bottom + shoes, or dress
    + shoes). When `new` is outerwear or an accessory, it is added on top of
    each base outfit. Optional layers are not counted, so the number reads as
    "different looks", not every permutation.
    """
    today = today or date.today()
    pool = sorted((p for p in closet if p.id != new.id), key=lambda p: p.id)
    rng = random.Random(0)
    seen: set[frozenset] = set()
    found: list[gen.Candidate] = []
    by_id = {p.id: p for p in pool} | {new.id: new}
    for assigned in _combos_with(new, pool):
        pieces = [p for _, p in sorted(assigned, key=lambda a: gen.SLOT_ORDER[a[0]])]
        key = frozenset(p.id for p in pieces)
        if key in seen or not outfit_ok(pieces):
            continue
        seen.add(key)
        data = tuple(p.item_data() for p in pieces)
        found.append(gen.Candidate(items=data, score=round(gen.score_combo(data, gen.WeatherContext(), today, rng), 4)))
    found.sort(key=lambda c: (-c.score, tuple(c.item_ids)))
    best = gen.diversify(found, k=TOP_CANDIDATES)
    return len(found), [Outfit(items=tuple(by_id[i] for i in c.item_ids), score=c.score) for c in best]


def outfit_count_label(count: int) -> str:
    return f"{OUTFIT_DISPLAY_CAP}+" if count > OUTFIT_DISPLAY_CAP else str(count)


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------
def find_duplicates(new: Piece, closet: Sequence[Piece]) -> list[Duplicate]:
    """Closet pieces with the same category, shade and silhouette.

    These are candidates: Claude confirms which ones a person would really
    call the same thing. Items with no subcategory ("other") never match,
    since there is nothing to compare.
    """
    shape = silhouette(new)
    if shape == "other":
        return []
    shade = color_shade(new.color)
    return [
        Duplicate(item=p, reason=f"also a {shade} {shape}")
        for p in closet
        if p.id != new.id and p.category == new.category and silhouette(p) == shape and color_shade(p.color) == shade
    ]


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------
def _in_seasons(piece: Piece, wanted: set[str]) -> bool:
    s = gen.parse_seasons(piece.season)
    return not s or "all" in s or bool(s & wanted)


def _gap_rules(events: Sequence[dict[str, Any]]) -> list[tuple[str, str, int, Callable[[Piece], bool]]]:
    """(label, category, want, matches) for every slot a working closet should cover."""
    rules: list[tuple[str, str, int, Callable[[Piece], bool]]] = []
    for cat in CORE_CATEGORIES:
        rules += [
            (f"neutral {cat}", cat, 2, lambda p: gen.color_family(p.color) == gen.NEUTRAL),
            (f"cold-weather {cat}", cat, 1, lambda p: _in_seasons(p, {"fall", "winter"})),
            (f"warm-weather {cat}", cat, 1, lambda p: _in_seasons(p, {"spring", "summer"})),
            (f"business {cat}", cat, 1, lambda p: formality_rank(p) >= FORMALITY_RANK["business"]),
        ]
    rules += [
        ("formal outerwear", "outerwear", 1, lambda p: p.formality == "formal"),
        ("formal shoes", "shoes", 1, lambda p: p.formality == "formal"),
        ("waterproof outerwear", "outerwear", 1, lambda p: p.waterproof),
        ("water-resistant shoes", "shoes", 1, lambda p: p.waterproof),
        ("warm winter coat", "outerwear", 1,
         lambda p: silhouette(p) == "coat" and any(w in (p.material or "").lower() for w in WARM_MATERIALS)),
        ("dark tailored trousers", "bottoms", 1,
         lambda p: silhouette(p) == "trousers" and color_shade(p.color) in DARK_SHADES and formality_rank(p) >= 1),
    ]
    # Calendar needs, the same triggers as tools/gaps.py.
    texts = [f"{e.get('name', '')} {e.get('dress_code_hint', '')}".lower() for e in events]
    if any("black tie" in t or "gala" in t for t in texts):
        rules.append(("formal evening outfit", "dresses", 1, lambda p: p.formality == "formal"))
    if any(is_athletic(t) for t in texts):
        rules.append(("workout clothes", "activewear", 1, lambda p: True))
    return rules


def find_gaps(closet: Sequence[Piece], events: Sequence[dict[str, Any]] = ()) -> list[Gap]:
    """Slots the closet leaves empty (0 items) or thin (fewer than the slot wants)."""
    gaps = []
    for label, cat, want, matches in _gap_rules(events):
        count = sum(1 for p in closet if p.category == cat and matches(p))
        if count < want:
            gaps.append(Gap(label=label, category=cat, count=count, want=want, matches=matches))
    return gaps


def gaps_filled(new: Piece, gaps: Sequence[Gap]) -> list[str]:
    return [g.label for g in gaps if new.category == g.category and g.matches(new)]


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
def calendar_matches(
    new: Piece, events: Sequence[dict[str, Any]], today: Optional[date] = None, days: int = CALENDAR_WINDOW_DAYS,
) -> list[dict[str, str]]:
    """Upcoming events the piece is dressed right for, in that event's season."""
    today = today or date.today()
    end = today + timedelta(days=days)
    out = []
    for e in events:
        raw = e.get("date")
        try:
            d = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if not (today <= d <= end):
            continue
        target = _dress_target(f"{e.get('dress_code_hint') or ''} {e.get('name') or ''}")
        if target is None:
            fits = new.category == "activewear" or gen.normalize_style(new.style) == "sporty"
        else:
            fits = abs(formality_rank(new) - target) <= EVENT_FORMALITY_TOLERANCE
        if fits and _in_seasons(new, {_season_of(d)}):
            out.append({"event": e.get("name") or "Event", "date": d.isoformat()})
    return out


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
def baseline_score(outfit_count: int, fills_gap: bool, calendar_count: int, duplicate_count: int) -> int:
    score = (
        BASE_SCORE
        + min(PER_OUTFIT * outfit_count, OUTFIT_CAP)
        + (GAP_BONUS if fills_gap else 0)
        + min(PER_EVENT * calendar_count, EVENT_CAP)
        - min(PER_DUPLICATE * duplicate_count, DUPLICATE_CAP)
    )
    return max(0, min(100, score))


def verdict(score: float) -> str:
    if score >= GREAT_BUY_MIN:
        return "great_buy"
    if score >= MAYBE_MIN:
        return "maybe"
    return "skip"


def assess(
    new: Piece, closet: Sequence[Piece], events: Sequence[dict[str, Any]] = (),
    today: Optional[date] = None, gaps: Optional[Sequence[Gap]] = None,
) -> Assessment:
    """Run the whole engine for one piece. Pass `gaps` to reuse them across many pieces."""
    today = today or date.today()
    count, candidates = count_outfits(new, closet, today)
    dups = find_duplicates(new, closet)
    filled = gaps_filled(new, find_gaps(closet, events) if gaps is None else gaps)
    matches = calendar_matches(new, events, today)
    score = baseline_score(count, bool(filled), len(matches), len(dups))
    return Assessment(
        outfit_count=count, candidates=candidates, duplicates=dups, gaps_filled=filled,
        calendar_matches=matches, score=score, verdict=verdict(score),
    )
