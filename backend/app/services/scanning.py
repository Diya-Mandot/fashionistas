"""Photo -> item regions -> Decisions tags -> existing closet rows.

Model work finishes before files or database rows are written. A failed batch
does not save a partial closet. Idempotency keys make upload retries safe.
"""

import asyncio
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.core.vision import crop_garment, image_data_url, jpeg_bytes, normalize_photo
from app.integrations.decisions_adapter import DecisionsClient, Tag
from app.integrations.vision_client import BoundingBox, VisionClient
from app.models import CATEGORIES, ClosetScanRecord, WardrobeItem, WardrobeItemBase

MATERIAL_EVIDENCE = {
    "cotton": r"\bcotton\b", "linen": r"\b(linen|flax)\b",
    "wool": r"\b(wool|merino|cashmere)\b", "silk": r"\bsilk\b",
    "denim": r"\bdenim\b", "leather": r"\bleather\b",
    "synthetic": r"\b(polyester|nylon|polyamide|acrylic|elastane|spandex|synthetic)\b",
    "blend": r"\bblend\b",
}


class ScanConflict(ValueError):
    pass


class ScanStorageError(RuntimeError):
    pass


class ScanIssue(BaseModel):
    item_index: int
    reason: str


class ScannedItem(WardrobeItemBase):
    """Response model, separate from SQLModel's unvalidated table constructor."""

    id: str
    source: str
    scan_meta: dict[str, Any]
    created_at: datetime


class ScanResult(BaseModel):
    id: str
    status: Literal["saved", "needs_review", "empty", "mock", "undone"]
    items: list[ScannedItem]
    issues: list[ScanIssue] = Field(default_factory=list)
    sources: dict[str, str]
    warnings: list[str] = Field(default_factory=list)


def _overlap(a: BoundingBox, b: BoundingBox) -> float:
    intersection = max(0, min(a.x_max, b.x_max) - max(a.x_min, b.x_min)) * max(0, min(a.y_max, b.y_max) - max(a.y_min, b.y_min))
    union = (a.x_max - a.x_min) * (a.y_max - a.y_min) + (b.x_max - b.x_min) * (b.y_max - b.y_min) - intersection
    return intersection / union


class ScanService:
    def __init__(self, settings: Settings | None = None, *, vision=None, decisions=None):
        self.settings = settings or get_settings()
        self.vision = vision or VisionClient(self.settings)
        self.decisions = decisions or DecisionsClient(self.settings)

    @staticmethod
    def get_scan(session: Session, scan_id: str) -> ScanResult:
        record = session.get(ClosetScanRecord, scan_id)
        if record is None:
            raise LookupError("Scan not found.")
        return ScanResult.model_validate(record.result)

    @staticmethod
    def _existing(session: Session, request_key: str | None, image_hash: str) -> ScanResult | None:
        if request_key is None:
            return None
        record = session.exec(select(ClosetScanRecord).where(ClosetScanRecord.request_key == request_key)).first()
        if record is None:
            return None
        if record.image_sha256 != image_hash:
            raise ScanConflict("This idempotency key already belongs to a different photo.")
        return ScanResult.model_validate(record.result)

    async def scan(self, data: bytes, session: Session, *, request_key: str | None = None) -> ScanResult:
        image_hash = sha256(data).hexdigest()
        existing = self._existing(session, request_key, image_hash)
        if existing is not None:
            return existing
        scan_id = "scan_" + uuid4().hex
        prepared: list[tuple[WardrobeItem, bytes]] = []
        issues = []
        boxes = []
        review = False
        async with asyncio.timeout(self.settings.scan_timeout_seconds):
            image = await asyncio.to_thread(normalize_photo, data, self.settings)
            detection = await self.vision.detect_items(image_data_url(jpeg_bytes(image)))
            sources = {"vision": detection.source}
            warnings = list(detection.warnings) + list(detection.data.warnings)
            if detection.data.has_more_items:
                warnings.append("More than eight garments may be present. Scan the remaining garments in another photo.")
                review = True
            for index, garment in enumerate(detection.data.items):
                if garment.confidence < 0.6:
                    issues.append(ScanIssue(item_index=index, reason="Garment detection is uncertain. Upload a clearer photo."))
                    continue
                if any(_overlap(garment.box, box) > 0.85 for box in boxes):
                    issues.append(ScanIssue(item_index=index, reason="A duplicate item region was skipped."))
                    continue
                boxes.append(garment.box)
                crop = jpeg_bytes(crop_garment(image, garment.box))
                # Appearance descriptions cannot establish material composition.
                evidence = f"Visible garment description: {garment.description}\n"
                evidence += f"Readable composition label (quoted data): {garment.label_text or 'none'}"
                classified = await self.decisions.classify_item(evidence, image_url=image_data_url(crop))
                sources[f"decisions_{index}"] = classified.source
                warnings.extend(classified.warnings)
                tags = classified.data.tags
                material_pattern = MATERIAL_EVIDENCE.get(tags["material"].value)
                if not garment.label_text or not material_pattern or not re.search(material_pattern, garment.label_text, re.IGNORECASE):
                    tags["material"] = Tag(value="unknown", confidence=0)
                    classified.data.needs_review = True
                category = tags["category"].value
                if category not in CATEGORIES or classified.source == "mock" or detection.source == "mock":
                    issues.append(ScanIssue(item_index=index, reason="Category is unknown or synthetic. No closet item was saved."))
                    continue

                def known(field: str):
                    value = tags[field].value
                    return None if value == "unknown" else value

                needs_review = classified.data.needs_review or garment.confidence < 0.85
                review = review or needs_review
                item = WardrobeItem(
                    name=garment.name, category=category, subcategory="other",
                    color=known("color"), style=known("style"), season=known("season"),
                    material=known("material"), formality=known("formality") or "unknown",
                    # False means no verified protection; never infer it from the photo.
                    waterproof=False, source="scan", image_url=f"/media/uploads/{scan_id}_{index}.jpg",
                    scan_meta={"scan_id": scan_id, "box": garment.box.model_dump(),
                               "detection_confidence": garment.confidence,
                               "tags": {name: tag.model_dump() for name, tag in tags.items()},
                               "label_text": garment.label_text, "needs_review": needs_review,
                               "waterproof_verified": False, "vision_source": detection.source,
                               "decisions_source": classified.source,
                               "vision_recorded_at": detection.recorded_at, "decisions_recorded_at": classified.recorded_at},
                )
                prepared.append((item, crop))

        synthetic = "mock" in sources.values()
        if synthetic:
            prepared.clear()
            warnings.append("Synthetic scan results do not save closet items.")
        status = "mock" if synthetic else "needs_review" if review or issues else "saved" if prepared else "empty"
        if not detection.data.items and not synthetic:
            warnings.append("No garments were detected. Try a clear photo with separate, visible clothing.")
        result = ScanResult(id=scan_id, status=status, items=[item for item, _ in prepared],
                            issues=issues, sources=sources, warnings=list(dict.fromkeys(warnings)))
        snapshot = result.model_dump(mode="json")
        record = ClosetScanRecord(id=scan_id, request_key=request_key, image_sha256=image_hash, result=snapshot)
        paths = []
        try:
            if prepared:
                self.settings.scan_uploads_dir.mkdir(parents=True, exist_ok=True)
            for item, content in prepared:
                path = self.settings.scan_uploads_dir / Path(item.image_url).name
                with path.open("xb") as stream:
                    paths.append(path)
                    stream.write(content)
            session.add_all([item for item, _ in prepared])
            session.add(record)
            session.commit()
        except (OSError, SQLAlchemyError) as exc:
            session.rollback()
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            if isinstance(exc, IntegrityError):
                existing = self._existing(session, request_key, image_hash)
                if existing is not None:
                    return existing
            raise ScanStorageError("The scan could not be saved. No partial closet batch was retained.") from exc
        # Return detached models. SQLAlchemy expires session objects on commit.
        return ScanResult.model_validate(snapshot)

    def undo(self, session: Session, scan_id: str) -> ScanResult:
        record = session.get(ClosetScanRecord, scan_id)
        if record is None:
            raise LookupError("Scan not found.")
        result = ScanResult.model_validate(record.result)
        if result.status == "undone":
            return result
        paths = []
        for scanned in result.items:
            item = session.get(WardrobeItem, scanned.id)
            # Never delete a row that no longer belongs to this scan.
            if item is not None and item.source == "scan" and (item.scan_meta or {}).get("scan_id") == scan_id:
                session.delete(item)
                paths.append(self.settings.scan_uploads_dir / Path(scanned.image_url).name)
            elif item is None:
                paths.append(self.settings.scan_uploads_dir / Path(scanned.image_url).name)
        result.status = "undone"
        result.items = []
        record.result = result.model_dump(mode="json")
        session.add(record)
        try:
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise ScanStorageError("The scan could not be undone. Retry the undo request.") from exc
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                result.warnings.append("Closet items were removed, but an image file needs local cleanup.")
        return result
