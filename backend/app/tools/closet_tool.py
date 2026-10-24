from datetime import date
from typing import Any, Optional

from sqlmodel import Session

from app.db import engine
from app.services.closet import list_items
from app.tools.context import RunContext, ToolOutput


def query_closet(ctx: RunContext, filters: Optional[dict[str, Any]] = None) -> ToolOutput:
    f = {k: v for k, v in (filters or {}).items() if k in {"category", "formality", "season", "color", "waterproof"} and v not in (None, "")}
    with Session(engine) as session:
        items = list_items(session, **f)
    compact = [
        {
            "id": i.id,
            "name": i.name,
            "category": i.category,
            "color": i.color,
            "formality": i.formality,
            "style": i.style,
            "season": i.season,
            "waterproof": i.waterproof,
            "days_since_worn": None if i.last_worn is None else (ctx.today - i.last_worn).days,
            "times_worn": i.number_of_times_worn,
        }
        for i in items
    ]
    by_cat: dict[str, int] = {}
    for i in items:
        by_cat[i.category] = by_cat.get(i.category, 0) + 1
    waterproof_outer = sum(1 for i in items if i.category == "outerwear" and i.waterproof)
    filt = f" ({', '.join(f'{k}={v}' for k, v in f.items())})" if f else ""
    return ToolOutput(
        result={"count": len(compact), "items": compact, "summary": {"by_category": by_cat, "waterproof_outerwear": waterproof_outer}},
        title=f"Queried closet: {len(compact)} items{filt}",
        detail=", ".join(f"{n} {c}" for c, n in sorted(by_cat.items(), key=lambda x: -x[1])),
    )


def today_iso(d: date) -> str:
    return d.isoformat()
