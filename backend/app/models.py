"""Database tables. SQLite via SQLModel; tables are created on startup (no migrations).

WardrobeItem fields follow the capstone's ecostylistbe/app/models/wardrobe_item.py,
minus social/borrowing columns, plus `formality` and `waterproof`.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

CATEGORIES = ("tops", "bottoms", "dresses", "outerwear", "shoes", "accessories", "bags", "activewear")
FORMALITIES = ("casual", "smart casual", "business", "formal")
STYLES = ("casual", "smart casual", "formal", "streetwear", "sporty", "bohemian", "vintage")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class WardrobeItemBase(SQLModel):
    name: str
    category: str = Field(index=True)
    subcategory: str = "other"
    color: Optional[str] = None
    style: Optional[str] = None
    brand: Optional[str] = None
    season: Optional[str] = None
    material: Optional[str] = None
    formality: str = "casual"
    waterproof: bool = False
    image_url: str = ""
    last_worn: Optional[date] = None
    number_of_times_worn: int = 0
    is_favorite: bool = False


class WardrobeItem(WardrobeItemBase, table=True):
    __tablename__ = "wardrobe_items"

    id: str = Field(default_factory=lambda: new_id("itm"), primary_key=True)
    source: str = "seed"  # seed | scan | manual
    scan_meta: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentRunRecord(SQLModel, table=True):
    __tablename__ = "agent_runs"

    id: str = Field(default_factory=lambda: new_id("run"), primary_key=True)
    message: str
    home_city: Optional[str] = None
    status: str = "running"  # running | completed | failed
    plan: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    trace: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    sources: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
