from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel

from app.db import get_session
from app.models import WardrobeItem, WardrobeItemBase
from app.services.closet import list_items

router = APIRouter(prefix="/api/closet", tags=["closet"])


class WardrobeItemUpdate(SQLModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    color: Optional[str] = None
    style: Optional[str] = None
    brand: Optional[str] = None
    season: Optional[str] = None
    material: Optional[str] = None
    formality: Optional[str] = None
    waterproof: Optional[bool] = None
    is_favorite: Optional[bool] = None


@router.get("", response_model=list[WardrobeItem])
def get_closet(
    category: Optional[str] = None,
    formality: Optional[str] = None,
    season: Optional[str] = None,
    color: Optional[str] = None,
    waterproof: Optional[bool] = None,
    session: Session = Depends(get_session),
):
    return list_items(
        session, category=category, formality=formality, season=season, color=color, waterproof=waterproof
    )


@router.post("", response_model=WardrobeItem, status_code=201)
def create_item(body: WardrobeItemBase, session: Session = Depends(get_session)):
    item = WardrobeItem.model_validate(body, update={"source": "manual"})
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/{item_id}", response_model=WardrobeItem)
def update_item(item_id: str, body: WardrobeItemUpdate, session: Session = Depends(get_session)):
    item = session.get(WardrobeItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    item.sqlmodel_update(body.model_dump(exclude_unset=True))
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, session: Session = Depends(get_session)):
    item = session.get(WardrobeItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    session.delete(item)
    session.commit()
