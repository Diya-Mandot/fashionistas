"""Photo -> item attributes: upload validation, Google Vision, then Claude classify.

Shared by Scan (which saves the item right away) and Should I Buy This?
(which saves only when the user taps "I bought it"). Nothing here touches the
database.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import UploadFile

from app.core.vision import (
    ProviderUnavailableError,
    ValidatedImage,
    get_google_vision_service,
    local_dominant_colors,
    to_data_url,
    validate_upload,
)
from app.integrations.decisions_client import ItemClassification, ItemSignals, classify_item
from app.trace import Timer, TraceStep


@dataclass
class PhotoAnalysis:
    classification: ItemClassification
    image: ValidatedImage
    signals: ItemSignals
    trace: list[TraceStep]


async def analyze_photo(file: UploadFile) -> PhotoAnalysis:
    """Validate, run Vision (or the on-device fallback) and classify.

    Raises InvalidImageError for uploads that aren't usable images.
    """
    trace: list[TraceStep] = []

    t = Timer()
    original_type = file.content_type
    image = await validate_upload(file)
    converted = image.content_type == "image/jpeg" and (file.filename or "").lower().endswith((".heic", ".heif"))
    trace.append(
        TraceStep(
            kind="validation",
            tool="upload",
            title=f"Photo checked{' and converted from HEIC' if converted else ''}",
            detail=f"{image.filename} · {len(image.content) // 1024} KB",
            args={"filename": file.filename, "content_type": original_type},
            result={"stored_as": image.content_type, "bytes": len(image.content)},
            source="local",
            duration_ms=t.ms,
        )
    )

    # --- Google Vision -------------------------------------------------------
    vision = get_google_vision_service()
    t = Timer()
    signals = ItemSignals(filename=file.filename or "", image_sha=image.sha)
    try:
        v = await vision.annotate(image.content)
        signals.best_guess = v.best_guess
        signals.labels = (v.web_entities + v.labels)[:12]
        signals.ocr_material = v.ocr.get("material")
        signals.ocr_brand = v.ocr.get("brand")
        signals.ocr_size = v.ocr.get("size")
        signals.dominant_colors = v.dominant_colors
        label_bits = [x for x in (signals.ocr_brand, signals.ocr_material and f"{signals.ocr_material}") if x]
        trace.append(
            TraceStep(
                kind="tool_call",
                tool="google_vision",
                title=f"Vision: detected “{v.best_guess or (signals.labels[0] if signals.labels else 'garment')}”",
                detail=f"Label text: {', '.join(label_bits)}" if label_bits else "No readable label text",
                args={"features": ["WEB_DETECTION", "TEXT_DETECTION", "LABEL_DETECTION", "IMAGE_PROPERTIES"]},
                result={
                    "best_guess": v.best_guess,
                    "labels": signals.labels,
                    "ocr": v.ocr,
                    "dominant_colors": v.dominant_colors,
                },
                source="live",
                duration_ms=t.ms,
            )
        )
    except ProviderUnavailableError as exc:
        signals.dominant_colors = local_dominant_colors(image)
        trace.append(
            TraceStep(
                kind="fallback",
                tool="google_vision",
                title="Vision not available: used the photo itself + on-device colors",
                detail=f"{exc}. Dominant colors: {', '.join(signals.dominant_colors)}",
                result={"dominant_colors": signals.dominant_colors, "filename": signals.filename},
                source="local",
                duration_ms=t.ms,
            )
        )

    # --- Decisions classify --------------------------------------------------
    t = Timer()
    signals.image_data_url = to_data_url(image)
    cls = classify_item(signals)
    conf = cls.confidence
    avg_conf = round(sum(conf.values()) / max(1, len(conf)), 2)
    trace.append(
        TraceStep(
            kind="decision",
            tool="classify_item",
            title=(
                f"Decisions: {cls.category.title()} · {cls.formality.title()} · {cls.season.title()} · "
                f"{cls.material.title()} · Waterproof {'Yes' if cls.waterproof else 'No'}"
            ),
            detail=f"Average confidence {avg_conf:.2f}" + (f" · {cls.meta.note}" if cls.meta.note else ""),
            args={"signals": signals.model_dump(exclude={"image_data_url"}), **(cls.meta.request_preview or {})},
            result=cls.model_dump(exclude={"meta"}),
            source=cls.meta.source,
            duration_ms=t.ms,
        )
    )
    return PhotoAnalysis(classification=cls, image=image, signals=signals, trace=trace)


def scan_meta(analysis: PhotoAnalysis) -> dict:
    """What a saved WardrobeItem keeps about how it was recognised."""
    cls = analysis.classification
    return {"confidence": cls.confidence, "decisions_source": cls.meta.source, "vision": analysis.signals.model_dump()}
