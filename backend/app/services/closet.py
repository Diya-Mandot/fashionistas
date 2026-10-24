"""Closet queries shared by the HTTP router and the agent's query_closet tool."""

from typing import Optional

from sqlmodel import Session, select

from app.models import WardrobeItem


def list_items(
    session: Session,
    *,
    category: Optional[str] = None,
    formality: Optional[str] = None,
    season: Optional[str] = None,
    color: Optional[str] = None,
    waterproof: Optional[bool] = None,
) -> list[WardrobeItem]:
    stmt = select(WardrobeItem).order_by(WardrobeItem.category, WardrobeItem.name)
    if category:
        stmt = stmt.where(WardrobeItem.category == category.lower())
    if formality:
        stmt = stmt.where(WardrobeItem.formality == formality.lower())
    if waterproof is not None:
        stmt = stmt.where(WardrobeItem.waterproof == waterproof)
    items = list(session.exec(stmt))
    if season:
        s = season.lower()
        items = [i for i in items if i.season and (s in i.season.lower() or "all" in i.season.lower())]
    if color:
        c = color.lower()
        items = [i for i in items if i.color and c in i.color.lower()]
    return items
