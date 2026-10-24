"""Import a folder of real clothing photos into the demo closet.

    cd backend && uv run python scripts/import_photos.py ~/Desktop/closet-photos
    make reset            # load them into the running app

Each photo is converted to JPEG (HEIC supported), downscaled, copied into
seed_images/photos/, and classified with the same pipeline as the Scan page
(Google Vision if configured -> Decisions API classify_item; mock without a key).
Results go to seed_images/photos/manifest.json, which seed.py reads, so every
photo becomes a closet item that survives `make reset`. Edit manifest.json by hand
to fix anything. Re-run with --reclassify after adding OPENAI_API_KEY to upgrade
mock classifications to live ones (hand-labelled entries are kept unless
--include-manual is passed).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

from PIL import Image, ImageOps  # noqa: E402

from app.core.vision import (  # noqa: E402
    ProviderUnavailableError,
    ValidatedImage,
    get_google_vision_service,
    heif_to_jpeg,
    is_heif,
    local_dominant_colors,
    to_data_url,
)
from app.integrations.decisions_client import ItemSignals, classify_item  # noqa: E402

PHOTOS = BACKEND / "seed_images" / "photos"
MANIFEST = PHOTOS / "manifest.json"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_SIDE = 1200


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def next_id(manifest: list[dict]) -> str:
    used = {int(m.group(1)) for e in manifest if (m := re.match(r"itm_photo(\d+)$", e.get("id", "")))}
    return f"itm_photo{max(used, default=0) + 1:02d}"


def to_jpeg(path: Path) -> bytes:
    raw = path.read_bytes()
    if is_heif(raw):
        raw = heif_to_jpeg(raw)
    with Image.open(BytesIO(raw)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=86)
    return buf.getvalue()


def classify(content: bytes, filename: str) -> dict:
    image = ValidatedImage(content=content, filename=filename, content_type="image/jpeg")
    signals = ItemSignals(filename=filename, image_sha=image.sha)
    vision = get_google_vision_service()
    try:
        v = asyncio.run(vision.annotate(content))
        signals.best_guess, signals.labels = v.best_guess, (v.web_entities + v.labels)[:12]
        signals.ocr_material, signals.ocr_brand, signals.dominant_colors = v.ocr.get("material"), v.ocr.get("brand"), v.dominant_colors
        vision_src = "live"
    except ProviderUnavailableError:
        signals.dominant_colors = local_dominant_colors(image)
        vision_src = "local"
    signals.image_data_url = to_data_url(image)
    c = classify_item(signals)
    return {
        "name": c.name, "category": c.category, "subcategory": c.subcategory, "color": c.color, "style": c.style,
        "formality": c.formality, "season": c.season, "material": c.material, "waterproof": c.waterproof,
        "brand": signals.ocr_brand, "classified_by": {"vision": vision_src, "decisions": c.meta.source},
        "confidence": c.confidence,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", type=Path, help="Folder of photos to import")
    ap.add_argument("--reclassify", action="store_true", help="Re-run classification for photos already in the manifest")
    ap.add_argument("--include-manual", action="store_true", help="With --reclassify, also overwrite hand-labelled entries")
    args = ap.parse_args()

    PHOTOS.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    by_file = {e["file"]: e for e in manifest}

    if args.folder:
        files = sorted(p for p in args.folder.expanduser().iterdir() if p.suffix.lower() in EXTS)
        if not files:
            print(f"No images found in {args.folder}")
            return 1
        known_sources = {e.get("source_file"): e for e in manifest}
        for path in files:
            entry = known_sources.get(path.name)
            if entry is None:
                n = len(by_file) + 1
                entry = {"id": next_id(list(by_file.values())), "file": f"{n:02d}-{slug(path.stem) or 'photo'}.jpg", "source_file": path.name}
            try:
                content = to_jpeg(path)
            except Exception as exc:
                print(f"  skip {path.name}: {exc}")
                continue
            (PHOTOS / entry["file"]).write_bytes(content)
            manual = entry.get("classified_by", {}).get("decisions") == "manual"
            if "category" not in entry or (args.reclassify and (not manual or args.include_manual)):
                entry.update(classify(content, path.name))
            entry.setdefault("days_since_worn", None)
            entry.setdefault("times_worn", 0)
            by_file[entry["file"]] = entry
            print(f"  {path.name:40} -> {entry.get('name')} · {entry.get('category')} · {entry.get('formality')} [{entry.get('classified_by', {}).get('decisions')}]")
    elif args.reclassify:
        for name, entry in by_file.items():
            if entry.get("classified_by", {}).get("decisions") == "manual" and not args.include_manual:
                continue
            entry.update(classify((PHOTOS / name).read_bytes(), name))
            print(f"  {name:40} -> {entry['name']} [{entry['classified_by']['decisions']}]")
    else:
        ap.print_help()
        return 1

    manifest = sorted(by_file.values(), key=lambda e: e["file"])
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    extras = manifest
    wet = [e["file"] for e in extras if e.get("category") == "outerwear" and e.get("waterproof")]
    print(f"\n{len(manifest)} photos in manifest.")
    if wet:
        print(f"Heads up: {wet} classified as WATERPROOF outerwear, so the rain-gap demo won't trigger. "
              "Set waterproof to false in manifest.json if that's wrong.")
    if any(e.get("classified_by", {}).get("decisions") == "mock" for e in extras):
        print("Some items were classified by the MOCK classifier (no API key). After adding OPENAI_API_KEY run: "
              "uv run python scripts/import_photos.py --reclassify")
    print("Now run `make reset` (with the backend running) to load them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
