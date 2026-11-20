"""Agentic closet scan: upload -> Google Vision -> Decisions classify -> auto-save."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from app.config import get_settings
from app.core.vision import InvalidImageError
from app.db import get_session
from app.models import WardrobeItem, new_id
from app.services.item_analysis import analyze_photo, scan_meta
from app.trace import TraceStep

router = APIRouter(prefix="/api/closet", tags=["scan"])


class ScanResponse(BaseModel):
    item: WardrobeItem
    trace: list[TraceStep]


@router.post("/scan", response_model=ScanResponse)
async def scan_item(file: UploadFile = File(...), session: Session = Depends(get_session)):
    try:
        analysis = await analyze_photo(file)
    except InvalidImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    cls, image, trace = analysis.classification, analysis.image, analysis.trace

    item_id = new_id("itm")
    suffix = Path(image.filename).suffix or ".jpg"
    uploads = Path(get_settings().uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / f"{item_id}{suffix}").write_bytes(image.content)
    item = WardrobeItem(
        id=item_id,
        name=cls.name,
        category=cls.category,
        subcategory=cls.subcategory,
        color=cls.color,
        style=cls.style,
        brand=analysis.signals.ocr_brand,
        season=cls.season,
        material=cls.material,
        formality=cls.formality,
        waterproof=cls.waterproof,
        image_url=f"/media/uploads/{item_id}{suffix}",
        source="scan",
        scan_meta=scan_meta(analysis),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    trace.append(
        TraceStep(kind="final", tool="closet", title="Saved to closet", detail=item.name, result={"item_id": item.id}, source="local")
    )
    return ScanResponse(item=item, trace=trace)
