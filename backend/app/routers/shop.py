"""Shop Your Gaps: catalog products ranked by how well they fit your closet."""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.core import compatibility as compat
from app.db import engine, get_session
from app.models import WardrobeItem
from app.services import calendar_source
from app.services.catalog import shop

router = APIRouter(prefix="/api/shop", tags=["shop"])
log = logging.getLogger(__name__)


def _shop_for(session: Session, category: Optional[str] = None, max_price: Optional[float] = None) -> dict[str, Any]:
    today = date.today()
    closet = [compat.as_piece(i) for i in session.exec(select(WardrobeItem))]
    events = calendar_source.upcoming_events(today, compat.CALENDAR_WINDOW_DAYS)
    return shop(closet, events, today, category=(category or None), max_price=max_price)


def warm_cache_in_background() -> None:
    """Score the catalog once at startup so the first Shop visit doesn't wait on ~1,000 items."""

    def run() -> None:
        try:
            with Session(engine) as session:
                _shop_for(session)
        except Exception:  # best effort: the first request just scores it instead
            log.exception("shop cache warm-up failed")

    threading.Thread(target=run, name="shop-warmup", daemon=True).start()


@router.get("")
def shop_your_gaps(
    category: Optional[str] = Query(None, max_length=40),
    max_price: Optional[float] = Query(None, gt=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _shop_for(session, category, max_price)
