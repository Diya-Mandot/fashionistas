"""Import one confirmed order atomically across the Gmail and MCP entry points."""

import hashlib
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session

from app.db import engine
from app.models import ImportedReceipt, WardrobeItem

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Category = Literal["tops", "bottoms", "dresses", "outerwear", "shoes", "accessories", "bags", "activewear"]


class ReceiptItem(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    category: Category
    color: ShortText | None = None
    brand: ShortText | None = None
    subcategory: ShortText = "other"
    quantity: int = Field(default=1, ge=1, le=20)


class Receipt(BaseModel):
    merchant: ShortText
    order_number: ShortText
    items: list[ReceiptItem] = Field(min_length=1, max_length=40)


class ReceiptResult(BaseModel):
    status: Literal["imported", "already_imported"]
    item_ids: list[str]


def _order_key(receipt: Receipt) -> str:
    # Match differences in spacing, capitalization, and order-number prefixes
    # such as a leading #. Preserve other punctuation in order numbers.
    merchant = " ".join(receipt.merchant.casefold().split())
    order_number = "".join(receipt.order_number.casefold().lstrip("#").split())
    return hashlib.sha256(f"{merchant}\n{order_number}".encode()).hexdigest()


def import_receipt(receipt: Receipt) -> ReceiptResult:
    order_id = _order_key(receipt)
    garments = [
        WardrobeItem(source="receipt", **item.model_dump(exclude={"quantity"}))
        for item in receipt.items
        for _ in range(item.quantity)
    ]
    item_ids = [item.id for item in garments]
    with Session(engine) as session:
        claim = (
            insert(ImportedReceipt)
            .values(id=order_id, item_ids=item_ids)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(ImportedReceipt.id)
        )
        if session.execute(claim).scalar_one_or_none() is None:
            existing = session.get(ImportedReceipt, order_id)
            return ReceiptResult(status="already_imported", item_ids=existing.item_ids)
        session.add_all(garments)
        session.commit()
        return ReceiptResult(status="imported", item_ids=item_ids)
