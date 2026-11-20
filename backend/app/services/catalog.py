"""The mock partner catalog (catalog/catalog.json), scored against a closet.

Shop Your Gaps and the Stylist's partner picks both use the deterministic
compatibility score only: no Claude call per product. The same trust rule
applies everywhere: a product scoring under TRUST_MIN is never shown,
sponsored or not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Callable, Optional, Sequence

from app.config import BACKEND_DIR
from app.core import compatibility as compat

CATALOG_PATH = BACKEND_DIR / "catalog" / "catalog.json"
TRUST_MIN = compat.GREAT_BUY_MIN
PUBLIC_FIELDS = ("id", "name", "store", "price", "image", "category", "subcategory", "color", "formality",
                 "season", "material", "waterproof", "sponsored")


@lru_cache(maxsize=1)
def load_catalog() -> tuple[dict[str, Any], ...]:
    """Catalog entries, read once. Products whose photo hasn't been fetched yet get image None."""
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple({**p, "image": p.get("image")} for p in raw if p.get("id") and p.get("category"))


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


def shop(
    closet: Sequence[compat.Piece], events: Sequence[dict[str, Any]], today: date,
    category: Optional[str] = None, max_price: Optional[float] = None,
) -> dict[str, Any]:
    """Shop Your Gaps: the closet's gaps and the trusted products, best first."""
    catalog = load_catalog()
    gaps = compat.find_gaps(closet, events)
    wanted = [
        p for p in catalog
        if (not category or p["category"] == category) and (max_price is None or p["price"] <= max_price)
    ]
    scored = score_products(wanted, closet, events, today, gaps)
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
    wet = _has(t, "water", "rain")
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


def partner_picks(
    need: str, closet: Sequence[compat.Piece], events: Sequence[dict[str, Any]] = (),
    today: Optional[date] = None, limit: int = 2,
) -> list[dict[str, Any]]:
    """Up to `limit` trusted catalog products for one gap, ranked like Shop Your Gaps."""
    match = gap_filter(need)
    if match is None:
        return []
    products = [p for p in load_catalog() if match(p)]
    scored = score_products(products, closet, events, today or date.today())
    shown = sorted((s for s in scored if s.score >= TRUST_MIN), key=ScoredProduct.rank_key)
    return [s.to_dict() for s in shown[:limit]]
