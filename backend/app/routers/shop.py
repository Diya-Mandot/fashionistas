"""Shop Your Gaps: partner-catalog products ranked by how well they fit your closet."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.core import compatibility as compat
from app.db import get_session
from app.models import WardrobeItem
from app.services import calendar_source
from app.services.catalog import shop

router = APIRouter(prefix="/api/shop", tags=["shop"])


@router.get("")
def shop_your_gaps(
    category: Optional[str] = Query(None, max_length=40),
    max_price: Optional[float] = Query(None, gt=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    today = date.today()
    closet = [compat.as_piece(i) for i in session.exec(select(WardrobeItem))]
    return shop(closet, calendar_source.upcoming_events(today, compat.CALENDAR_WINDOW_DAYS), today, category=(category or None), max_price=max_price)
