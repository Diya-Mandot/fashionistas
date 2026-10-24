"""Upload validation and Google Vision, ported (slimmed) from the capstone's
ecostylistbe/app/core/closet_scan_service.py.

Kept: validate_upload with HEIC -> JPEG, parse_label_suggestions, the category
guesser, and a Vision adapter. Dropped: Cloudinary (images are stored under
backend/uploads/) and the SSRF-safe remote downloader (we never fetch remote images).

Vision is called over its REST API in a single request (web detection + OCR +
labels + dominant colors). Auth, in order: GOOGLE_VISION_API_KEY, then a
service-account file in GOOGLE_APPLICATION_CREDENTIALS, then gcloud Application
Default Credentials (`gcloud auth application-default login`), which is what
the capstone used.
"""

from __future__ import annotations

import base64
import hashlib
import re
import threading
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
import pillow_heif
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError

from app.config import get_settings

ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp"}
# MPO is a JPEG with extra embedded frames (e.g. iPhone depth/HDR); its first frame is plain JPEG.
PIL_CONTENT_TYPES = {"JPEG": "image/jpeg", "MPO": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
# Browsers often send HEIC as application/octet-stream or with no type at all.
HEIF_UPLOAD_TYPES = {"image/heic", "image/heif", "application/octet-stream", ""}
UNSUPPORTED_TYPE_MESSAGE = "Use a JPG, PNG, WEBP, or HEIC image."
_HEIF_DECODE_SLOTS = threading.BoundedSemaphore(2)
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1")

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


class InvalidImageError(ValueError):
    """The user's upload is not an acceptable image. The message is safe to show."""


class ProviderUnavailableError(RuntimeError):
    """Google Vision is missing, misconfigured, or failed."""


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    filename: str
    content_type: str

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.content).hexdigest()[:16]


def is_heif(content: bytes) -> bool:
    return len(content) >= 12 and content[4:8] == b"ftyp" and content[8:12] in _HEIF_BRANDS


def _validate_image_bytes(content: bytes, *, declared_content_type: str, filename: str) -> ValidatedImage:
    """Check that image bytes really are the type they claim, and within limits."""
    s = get_settings()
    if not content:
        raise InvalidImageError("The image is empty.")
    if len(content) > s.scan_max_image_bytes:
        raise InvalidImageError("The image is too large.")
    if declared_content_type.lower() not in ALLOWED_UPLOAD_TYPES:
        raise InvalidImageError("Use a JPG, PNG, or WEBP image.")
    try:
        with Image.open(BytesIO(content)) as image:
            detected_type = PIL_CONTENT_TYPES.get(image.format or "")
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("The file is not a valid image.") from exc
    if detected_type != declared_content_type.lower():
        raise InvalidImageError("The image content does not match its file type.")
    if width <= 0 or height <= 0 or width * height > s.scan_max_image_pixels:
        raise InvalidImageError("The image dimensions are too large.")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[detected_type]
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(filename).stem)[:60] or "garment"
    return ValidatedImage(content=content, filename=f"{safe_stem}{suffix}", content_type=detected_type)


def heif_to_jpeg(content: bytes) -> bytes:
    """Decode a HEIC/HEIF photo and re-encode it as JPEG (rotation applied, EXIF/GPS dropped)."""
    try:
        heif = pillow_heif.open_heif(content)
        width, height = heif.size
    except (ValueError, RuntimeError, OSError) as exc:
        raise InvalidImageError("The file is not a valid image.") from exc
    if width <= 0 or height <= 0 or width * height > get_settings().scan_max_image_pixels:
        raise InvalidImageError("The image dimensions are too large.")
    with _HEIF_DECODE_SLOTS:
        try:
            decoded = heif.to_pillow()
            image = decoded.convert("RGB")
        except (ValueError, RuntimeError, OSError) as exc:
            raise InvalidImageError("The file is not a valid image.") from exc
        output = BytesIO()
        icc_profile = decoded.info.get("icc_profile")
        image.save(output, format="JPEG", quality=90, **({"icc_profile": icc_profile} if icc_profile else {}))
    return output.getvalue()


async def validate_upload(file: UploadFile) -> ValidatedImage:
    """Validate a user's photo upload, converting HEIC to JPEG first."""
    max_bytes = get_settings().scan_max_image_bytes
    declared_type = (file.content_type or "").lower()
    if declared_type not in ALLOWED_UPLOAD_TYPES | HEIF_UPLOAD_TYPES:
        raise InvalidImageError(UNSUPPORTED_TYPE_MESSAGE)
    content = await file.read(max_bytes + 1)
    await file.close()
    filename = file.filename or "garment"
    if is_heif(content) and (declared_type in HEIF_UPLOAD_TYPES or filename.lower().endswith((".heic", ".heif"))):
        if len(content) > max_bytes:
            raise InvalidImageError("The image is too large.")
        content = await run_in_threadpool(heif_to_jpeg, content)
        declared_type = "image/jpeg"
    elif declared_type not in ALLOWED_UPLOAD_TYPES:
        raise InvalidImageError(UNSUPPORTED_TYPE_MESSAGE)
    return _validate_image_bytes(content, declared_content_type=declared_type, filename=filename)


def to_data_url(image: ValidatedImage, max_side: int = 768) -> str:
    """Downscaled JPEG data URL for sending the photo to the Decisions API."""
    with Image.open(BytesIO(image.content)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# Text helpers (ported)
# ---------------------------------------------------------------------------
def _clean_text(value: object, max_length: int) -> Optional[str]:
    text = " ".join(str(value or "").split()).strip()
    return text[:max_length] or None


def guess_category(text: str) -> Optional[str]:
    """Guess a closet category from free text. First match wins, so order matters
    (shoes first: "dress shoes" -> shoes; dresses before tops: "shirt dress" -> dresses)."""
    lowered = text.lower()
    mappings = (
        ("shoes", ("shoe", "sneaker", "boot", "sandal", "heel", "loafer", "footwear")),
        ("dresses", ("dress", "gown", "jumpsuit", "romper", "playsuit", "overalls", "dungarees")),
        ("outerwear", ("jacket", "coat", "blazer", "cardigan", "vest", "parka", "trench", "raincoat", "anorak")),
        ("bottoms", ("pants", "jeans", "trouser", "shorts", "skirt", "denim")),
        ("bags", ("bag", "purse", "backpack", "handbag", "tote")),
        ("accessories", ("hat", "scarf", "belt", "sunglasses", "jewelry", "watch", "earring", "necklace")),
        ("activewear", ("sports bra", "tracksuit", "gym wear", "leggings")),
        ("tops", ("shirt", "top", "blouse", "sweater", "hoodie", "polo", "tee", "knit")),
    )
    for category, words in mappings:
        if any(word in lowered for word in words):
            return category
    return None


_KNOWN_BRANDS = (
    "Levi's", "Patagonia", "Uniqlo", "Zara", "H&M", "Everlane", "Nike", "Adidas", "Madewell", "J.Crew",
    "Gap", "COS", "Aritzia", "Reformation", "AllSaints", "Carhartt", "The North Face", "Arc'teryx",
)


def parse_label_suggestions(text: str) -> dict[str, Optional[str]]:
    """Extract a small safe subset from OCR text; never return the raw label text."""
    compact = " ".join(text.split())[:4000]
    size_match = re.search(
        r"\bsize\s*[:#-]?\s*(XXS|XS|S|M|L|XL|XXL|2XL|3XL|4XL|\d{1,2}(?:\.5)?)\b", compact, flags=re.IGNORECASE
    ) or re.search(r"\b(XXS|XS|XL|XXL|2XL|3XL)\b", compact)
    material_match = re.search(
        r"\b(organic cotton|cotton|polyester|wool|linen|silk|nylon|rayon|viscose|leather|cashmere|denim)\b",
        compact,
        flags=re.IGNORECASE,
    )
    brand = next((b for b in _KNOWN_BRANDS if re.search(rf"\b{re.escape(b)}\b", compact, flags=re.IGNORECASE)), None)
    return {
        "size": size_match.group(1).upper() if size_match else None,
        "material": material_match.group(1).lower() if material_match else None,
        "brand": brand,
    }


_NAMED_COLORS = {
    "black": (25, 25, 25), "white": (240, 240, 236), "grey": (128, 128, 128), "navy": (30, 40, 70),
    "blue": (60, 110, 180), "brown": (110, 70, 40), "tan": (190, 150, 105), "camel": (195, 155, 108),
    "beige": (220, 205, 180), "green": (60, 130, 80), "red": (180, 40, 45), "pink": (230, 150, 170),
    "yellow": (230, 200, 60), "orange": (225, 120, 50), "purple": (120, 70, 150),
}


def nearest_color_name(rgb: tuple[int, int, int]) -> str:
    return min(_NAMED_COLORS, key=lambda n: sum((a - b) ** 2 for a, b in zip(rgb, _NAMED_COLORS[n])))


def local_dominant_colors(image: ValidatedImage, k: int = 3) -> list[str]:
    """Cheap on-device fallback for dominant colors when Vision isn't available."""
    with Image.open(BytesIO(image.content)) as im:
        im = im.convert("RGB")
        im.thumbnail((96, 96))
        w, h = im.size
        # Ignore a border so plain backgrounds count less.
        crop = im.crop((w // 6, h // 6, w - w // 6, h - h // 6))
        quant = crop.quantize(colors=5)
        palette = quant.getpalette() or []
        counts = sorted(quant.getcolors() or [], reverse=True)
    names: list[str] = []
    for _count, idx in counts:
        rgb = tuple(palette[idx * 3 : idx * 3 + 3])
        name = nearest_color_name(rgb)  # type: ignore[arg-type]
        if name not in names:
            names.append(name)
    return names[:k]


# ---------------------------------------------------------------------------
# Google Vision
# ---------------------------------------------------------------------------
@dataclass
class VisionResult:
    best_guess: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    web_entities: list[str] = field(default_factory=list)
    ocr: dict[str, Optional[str]] = field(default_factory=dict)
    dominant_colors: list[str] = field(default_factory=list)
    ocr_excerpt: Optional[str] = None


VISION_SCOPE = "https://www.googleapis.com/auth/cloud-vision"
_adc_lock = threading.Lock()
_adc_creds = None


def _auth() -> tuple[dict[str, str], dict[str, str], str]:
    """Return (query params, headers, method label) for a Vision request."""
    global _adc_creds
    s = get_settings()
    key = s.google_vision_api_key.strip()
    if key:
        return {"key": key}, {}, "API key"
    try:
        import google.auth
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:
        raise ProviderUnavailableError("Google Vision is not configured") from exc
    with _adc_lock:
        try:
            if _adc_creds is None:
                path = s.google_application_credentials.strip()
                if path:
                    _adc_creds = service_account.Credentials.from_service_account_file(
                        str(Path(path).expanduser()), scopes=[VISION_SCOPE]
                    )
                else:
                    _adc_creds, _project = google.auth.default(scopes=[VISION_SCOPE])
            if not _adc_creds.valid:
                _adc_creds.refresh(Request())
        except Exception as exc:
            _adc_creds = None
            raise ProviderUnavailableError(
                "Google Vision is not configured (no API key, service account, or gcloud application-default login)"
            ) from exc
        headers = {"Authorization": f"Bearer {_adc_creds.token}"}
        quota = getattr(_adc_creds, "quota_project_id", None)
        if quota:
            headers["x-goog-user-project"] = quota
        label = "service account" if s.google_application_credentials.strip() else "gcloud credentials"
        return {}, headers, label


def vision_configured() -> bool:
    try:
        _auth()
        return True
    except ProviderUnavailableError:
        return False


class GoogleVisionService:
    """Small mockable adapter around the Google Cloud Vision REST API."""

    def configured(self) -> bool:
        return vision_configured()

    def _annotate_sync(self, content: bytes) -> VisionResult:
        s = get_settings()
        params, headers, _method = _auth()
        body = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(content).decode()},
                    "features": [
                        {"type": "WEB_DETECTION", "maxResults": 8},
                        {"type": "TEXT_DETECTION"},
                        {"type": "LABEL_DETECTION", "maxResults": 10},
                        {"type": "IMAGE_PROPERTIES"},
                    ],
                }
            ]
        }
        try:
            res = httpx.post(VISION_URL, params=params, headers=headers, json=body, timeout=s.vision_timeout_s)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Vision request failed: {type(exc).__name__}") from exc
        if res.status_code != 200:
            try:
                msg = res.json().get("error", {}).get("message", "")[:160]
            except ValueError:
                msg = ""
            raise ProviderUnavailableError(f"Vision returned HTTP {res.status_code} {msg}".strip())
        r = (res.json().get("responses") or [{}])[0]
        if r.get("error"):
            raise ProviderUnavailableError(f"Vision error: {r['error'].get('message', '')[:120]}")

        web = r.get("webDetection", {})
        guesses = [_clean_text(g.get("label"), 80) for g in web.get("bestGuessLabels", [])]
        entities = [_clean_text(e.get("description"), 60) for e in web.get("webEntities", []) if e.get("score", 0) > 0.4]
        labels = [_clean_text(lab.get("description"), 60) for lab in r.get("labelAnnotations", [])]
        text = (r.get("textAnnotations") or [{}])[0].get("description", "")
        colors = r.get("imagePropertiesAnnotation", {}).get("dominantColors", {}).get("colors", [])
        colors = sorted(colors, key=lambda c: c.get("pixelFraction", 0), reverse=True)
        color_names: list[str] = []
        for c in colors[:6]:
            rgb = c.get("color", {})
            name = nearest_color_name((int(rgb.get("red", 0)), int(rgb.get("green", 0)), int(rgb.get("blue", 0))))
            if name not in color_names:
                color_names.append(name)
        return VisionResult(
            best_guess=next((g for g in guesses if g), None),
            labels=[x for x in labels if x],
            web_entities=[x for x in entities if x][:6],
            ocr=parse_label_suggestions(text),
            dominant_colors=color_names[:3],
            ocr_excerpt=_clean_text(text, 80),
        )

    async def annotate(self, content: bytes) -> VisionResult:
        return await run_in_threadpool(self._annotate_sync, content)


def get_google_vision_service() -> GoogleVisionService:
    return GoogleVisionService()
