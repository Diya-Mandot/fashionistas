"""Validate photo bytes, normalize orientation, strip metadata, and crop garments."""

import base64
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.config import Settings

register_heif_opener()


class InvalidPhoto(ValueError):
    pass


def normalize_photo(data: bytes, settings: Settings) -> Image.Image:
    if not data or len(data) > settings.scan_max_image_bytes:
        raise InvalidPhoto("Upload a nonempty photo within the configured size limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                if probe.format not in {"JPEG", "PNG", "WEBP", "HEIF"}:
                    raise InvalidPhoto("Use a JPEG, PNG, WebP, or HEIC photo.")
                if probe.width * probe.height > settings.scan_max_image_pixels:
                    raise InvalidPhoto("The photo exceeds the pixel limit.")
                if getattr(probe, "is_animated", False):
                    raise InvalidPhoto("Animated images are not supported.")
                probe.verify()
            with Image.open(BytesIO(data)) as opened:
                oriented = ImageOps.exif_transpose(opened)
                oriented.thumbnail((2048, 2048))
                oriented.load()
                # A new canvas strips EXIF, GPS, filenames, and other metadata.
                canvas = Image.new("RGB", oriented.size, "white")
                if "A" in oriented.getbands() or "transparency" in oriented.info:
                    rgba = oriented.convert("RGBA")
                    canvas.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    canvas.paste(oriented.convert("RGB"))
                return canvas
    except InvalidPhoto:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidPhoto("The photo is corrupt, unsupported, or too large to decode.") from exc


def jpeg_bytes(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="JPEG", quality=90)
    return stream.getvalue()


def image_data_url(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def crop_garment(image: Image.Image, box) -> Image.Image:
    coordinates = (int(box.x_min * image.width), int(box.y_min * image.height),
                   int(box.x_max * image.width), int(box.y_max * image.height))
    if coordinates[2] - coordinates[0] < 4 or coordinates[3] - coordinates[1] < 4:
        raise InvalidPhoto("A detected garment is too small. Upload a closer photo.")
    return image.crop(coordinates)
