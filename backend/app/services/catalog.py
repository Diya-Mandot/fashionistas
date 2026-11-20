"""The shop catalog, scored against a closet.

Two sources, picked by the CATALOG_SOURCE setting:
  thrift (default) - live inventory from Utah thrift stores, written by
                     scripts/sync_thrift.py to catalog/thrift.json
  mock             - the hand-built partner catalog (catalog/catalog.json)
                     that the demo and tests are stacked against
If thrift.json hasn't been synced yet, the mock catalog is used.

Shop Your Gaps and the Stylist's partner picks both use the deterministic
compatibility score only: no Claude call per product. The same trust rule
applies everywhere: a product scoring under TRUST_MIN is never shown,
sponsored or not.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from app.config import BACKEND_DIR, get_settings
from app.core import compatibility as compat

CATALOG_PATH = BACKEND_DIR / "catalog" / "catalog.json"
THRIFT_PATH = BACKEND_DIR / "catalog" / "thrift.json"
TRUST_MIN = compat.GREAT_BUY_MIN
PUBLIC_FIELDS = ("id", "name", "store", "price", "image", "category", "subcategory", "color", "formality",
                 "season", "material", "waterproof", "sponsored", "url", "store_location", "sizes", "secondhand")

_lock = threading.Lock()
_compute_lock = threading.Lock()
_loaded: dict[str, Any] = {"key": None, "products": ()}
_scores: dict[tuple, list["ScoredProduct"]] = {}
_SCORE_CACHE_MAX = 8


def catalog_path() -> Path:
    if get_settings().catalog_source == "thrift" and THRIFT_PATH.exists():
        return THRIFT_PATH
    return CATALOG_PATH


def load_catalog() -> tuple[dict[str, Any], ...]:
    """Catalog entries, re-read whenever the file changes (a thrift sync). Missing photos get image None."""
    path = catalog_path()
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return ()
    with _lock:
        if _loaded["key"] == key:
            return _loaded["products"]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _loaded["products"]
        products = tuple({**p, "image": p.get("image")} for p in raw if p.get("id") and p.get("category"))
        _loaded.update(key=key, products=products)
        _scores.clear()
        return products


@dataclass(frozen=True)
class ScoredProduct:
    product: dict[str, Any]
    assessment: compat.Assessment

    @property
    def score(self) -> int:
        return self.assessment.score

    def rank_key(self) -> tuple:
        # Outfits first (at the displayed cap, so two "50+" items don't rank on
        # an invisible difference), then filling a gap, then the cheaper one.
        a = self.assessment
        return (-min(a.outfit_count, compat.OUTFIT_DISPLAY_CAP + 1), not a.gaps_filled, self.product["price"], self.product["id"])

    def to_dict(self) -> dict[str, Any]:
        a = self.assessment
        return {
            **{k: self.product.get(k) for k in PUBLIC_FIELDS},
            "outfit_count": a.outfit_count,
            "outfit_count_label": compat.outfit_count_label(a.outfit_count),
            "fills": a.gaps_filled,
            "score": a.score,
            "verdict": a.verdict,
        }


def score_products(
    products: Sequence[dict[str, Any]], closet: Sequence[compat.Piece], events: Sequence[dict[str, Any]],
    today: date, gaps: Optional[Sequence[compat.Gap]] = None,
) -> list[ScoredProduct]:
    gaps = compat.find_gaps(closet, events) if gaps is None else gaps
    return [ScoredProduct(p, compat.assess(compat.as_piece(p), closet, events, today, gaps=gaps)) for p in products]


def score_catalog(
    closet: Sequence[compat.Piece], events: Sequence[dict[str, Any]], today: date,
    gaps: Optional[Sequence[compat.Gap]] = None,
) -> list[ScoredProduct]:
    """The whole catalog scored against a closet, cached until the closet, calendar, day or catalog changes.

    The thrift catalog runs to ~1,000 items (a few seconds to score), so filtering
    by category or by Stylist gap reuses one scoring pass instead of redoing it.
    """
    catalog = load_catalog()
    key = (_loaded["key"], tuple(closet), json.dumps(list(events), sort_keys=True, default=str), today)
    with _lock:
        hit = _scores.get(key)
    if hit is not None:
        return hit
    # One scoring pass at a time: a request that arrives while the startup warm-up (or another
    # request) is scoring the same closet waits for that result instead of doing it twice.
    with _compute_lock:
        with _lock:
            hit = _scores.get(key)
        if hit is not None:
            return hit
        scored = score_products(catalog, closet, events, today, gaps)
        with _lock:
            if len(_scores) >= _SCORE_CACHE_MAX:
                _scores.pop(next(iter(_scores)))
            _scores[key] = scored
    return scored


def shop(
    closet: Sequence[compat.Piece], events: Sequence[dict[str, Any]], today: date,
    category: Optional[str] = None, max_price: Optional[float] = None,
) -> dict[str, Any]:
    """Shop Your Gaps: the closet's gaps and the trusted products, best first."""
    catalog = load_catalog()
    gaps = compat.find_gaps(closet, events)
    scored = [
        s for s in score_catalog(closet, events, today, gaps)
        if (not category or s.product["category"] == category) and (max_price is None or s.product["price"] <= max_price)
    ]
    shown = sorted((s for s in scored if s.score >= TRUST_MIN), key=ScoredProduct.rank_key)
    return {
        "gaps": [
            {
                "label": g.label, "category": g.category, "status": g.status, "count": g.count,
                "products": sum(1 for s in shown if g.label in s.assessment.gaps_filled),
            }
            for g in gaps
        ],
        "products": [s.to_dict() for s in shown],
        "hidden_by_trust_rule": len(scored) - len(shown),
        "categories": sorted({p["category"] for p in catalog}),
        "source": "thrift" if catalog_path() == THRIFT_PATH else "mock",
        "stores": sorted({p["store"] for p in catalog}),
        "trust_min": TRUST_MIN,
    }


# ---------------------------------------------------------------------------
# Partner picks on Stylist gap cards
# ---------------------------------------------------------------------------
_WARM = compat.WARM_MATERIALS


def _has(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def gap_filter(need: str) -> Optional[Callable[[dict[str, Any]], bool]]:
    """Catalog filter for a Stylist gap. The need is Claude's wording, so match on keywords.

    Covers the needs tools/gaps.py raises: waterproof outer layer,
    water-resistant shoes, warm winter coat, formal evening outfit, workout
    clothes, shoes. Order matters: "water-resistant shoes" is shoes, not a coat.
    """
    t = need.lower()
    wet = _has(t, "water", "rain", "snow")
    if _has(t, "glove", "mitten"):
        return lambda p: p["category"] == "accessories" and (p.get("subcategory") == "gloves" or _has(p["name"].lower(), "glove", "mitten"))
    if _has(t, "beanie", "hat", "toque"):
        return lambda p: (p["category"] == "accessories" and p.get("subcategory") == "hat"
                          and _has(f"{p['name']} {p.get('material') or ''}".lower(), *_WARM, "knit", "beanie", "mohair", "alpaca"))
    if _has(t, "base layer", "baselayer", "thermal"):
        return lambda p: p["category"] in ("activewear", "tops") and _has(f"{p['name']} {p.get('material') or ''}".lower(), "thermal", "merino", "base layer")
    if _has(t, "insulated", "puffer", "down jacket", "fleece"):
        return lambda p: (p["category"] == "outerwear" and p.get("subcategory") not in ("coat", "blazer")
                          and _has(f"{p['name']} {p.get('subcategory') or ''} {p.get('material') or ''}".lower(), "puffer", "down", "fleece", "insulated"))
    if _has(t, "formal", "evening", "black tie", "gala"):
        return lambda p: p["category"] == "dresses" and p.get("formality") == "formal"
    if _has(t, "workout", "gym", "athletic", "activewear", "exercise"):
        return lambda p: p["category"] == "activewear"
    if _has(t, "shoe", "boot", "footwear"):
        return (lambda p: p["category"] == "shoes" and bool(p.get("waterproof"))) if wet else (lambda p: p["category"] == "shoes")
    if wet:
        return lambda p: p["category"] == "outerwear" and bool(p.get("waterproof"))
    if _has(t, "coat", "winter", "warm"):
        return lambda p: (p["category"] == "outerwear" and p.get("subcategory") == "coat"
                          and _has((p.get("material") or "").lower(), *_WARM))
    return None


def gap_category(need: str) -> Optional[str]:
    """The Shop page category a gap belongs to, for the "browse the shop" link."""
    t = need.lower()
    if _has(t, "glove", "mitten", "beanie", "hat", "toque", "scarf"):
        return "accessories"
    if _has(t, "base layer", "baselayer", "thermal", "workout", "gym", "athletic", "activewear", "exercise"):
        return "activewear"
    if _has(t, "formal", "evening", "black tie", "gala"):
        return "dresses"
    if _has(t, "shoe", "boot", "footwear"):
        return "shoes"
    if _has(t, "coat", "jacket", "outer", "layer", "puffer", "fleece"):
        return "outerwear"
    return None


def partner_picks(
    need: str, closet: Sequence[compat.Piece], events: Sequence[dict[str, Any]] = (),
    today: Optional[date] = None, limit: int = 2,
) -> list[dict[str, Any]]:
    """Up to `limit` trusted catalog products for one gap, ranked like Shop Your Gaps.

    The Stylist's gaps come from the trip (weather, plans), not from the closet rules in
    compat.find_gaps, so a matching product earns no gap bonus in the cached score. A
    product offered on the gap card fills that gap by definition: credit it before the
    trust rule, the same way Shop Your Gaps credits a closet gap.
    """
    match = gap_filter(need)
    if match is None:
        return []
    scored = [_credit_gap(s, need) for s in score_catalog(closet, events, today or date.today()) if match(s.product)]
    shown = sorted((s for s in scored if s.score >= TRUST_MIN), key=ScoredProduct.rank_key)
    return [s.to_dict() for s in shown[:limit]]


def _credit_gap(s: ScoredProduct, need: str) -> ScoredProduct:
    a = s.assessment
    if a.gaps_filled:
        return s
    score = compat.baseline_score(a.outfit_count, True, len(a.calendar_matches), len(a.duplicates))
    return ScoredProduct(s.product, replace(a, gaps_filled=[need], score=score, verdict=compat.verdict(score)))
