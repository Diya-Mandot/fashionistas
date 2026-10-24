"""Import a folder of real clothing photos into the demo closet.

    cd backend && uv run python scripts/import_photos.py ~/Desktop/closet-photos
    make reset            # load them into the running app

Each photo is converted to JPEG (HEIC supported), downscaled, copied into
seed_images/photos/, and classified with the same pipeline as the Scan page
(Google Vision if configured -> Decisions API classify_item; mock without a key).
Results go to seed_images/photos/manifest.json, which seed.py reads:
  - a photo whose filename matches a demo item (e.g. "black-leather-moto-jacket.jpg"
    or "14-moto.jpg") REPLACES that item's illustration and keeps its attributes;
  - every other photo becomes an extra closet item.
Edit manifest.json by hand to fix anything. Re-run with --reclassify after adding
OPENAI_API_KEY to upgrade mock classifications to live ones.
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
from app.seed import _CLOSET  # noqa: E402

PHOTOS = BACKEND / "seed_images" / "photos"
MANIFEST = PHOTOS / "manifest.json"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_SIDE = 1200


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


SEED_SLUGS = {slug(row[1]): f"itm_seed{n:02d}" for n, row in enumerate(_CLOSET, start=1)}
SEED_ART = {f"{n:02d}-{row[0]}": f"itm_seed{n:02d}" for n, row in enumerate(_CLOSET, start=1)}


def match_seed(stem: str) -> str | None:
    s = slug(stem)
    if s in SEED_SLUGS:
        return SEED_SLUGS[s]
    if s.replace("_", "-") in SEED_ART:
        return SEED_ART[s.replace("_", "-")]
    m = re.match(r"^(\d{1,2})\b", s)
    if m and 1 <= int(m.group(1)) <= len(_CLOSET) and s.startswith(f"{int(m.group(1)):02d}-"):
        return f"itm_seed{int(m.group(1)):02d}"
    tokens = set(s.split("-"))
    best, best_overlap = None, 0
    for seed_slug, item_id in SEED_SLUGS.items():
        overlap = len(tokens & set(seed_slug.split("-")))
        if overlap > best_overlap:
            best, best_overlap = item_id, overlap
    return best if best_overlap >= 3 else None


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
    ap.add_argument("--no-replace", action="store_true", help="Never replace demo illustrations; import everything as extra items")
    args = ap.parse_args()

    PHOTOS.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    by_file = {e["file"]: e for e in manifest}

    if args.folder:
        files = sorted(p for p in args.folder.expanduser().iterdir() if p.suffix.lower() in EXTS)
        if not files:
            print(f"No images found in {args.folder}")
            return 1
        for path in files:
            out_name = f"{slug(path.stem) or 'photo'}.jpg"
            try:
                content = to_jpeg(path)
            except Exception as exc:
                print(f"  skip {path.name}: {exc}")
                continue
            (PHOTOS / out_name).write_bytes(content)
            replaces = None if args.no_replace else match_seed(path.stem)
            entry = by_file.get(out_name, {"file": out_name})
            entry["replaces"] = replaces
            if replaces is None and ("category" not in entry or args.reclassify):
                entry.update(classify(content, path.name))
            by_file[out_name] = entry
            what = f"replaces {replaces}" if replaces else f"{entry.get('name')} · {entry.get('category')} · {entry.get('formality')} [{entry.get('classified_by', {}).get('decisions')}]"
            print(f"  {path.name:40} -> {what}")
    elif args.reclassify:
        for name, entry in by_file.items():
            if entry.get("replaces"):
                continue
            entry.update(classify((PHOTOS / name).read_bytes(), name))
            print(f"  {name:40} -> {entry['name']} [{entry['classified_by']['decisions']}]")
    else:
        ap.print_help()
        return 1

    manifest = sorted(by_file.values(), key=lambda e: e["file"])
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    extras = [e for e in manifest if not e.get("replaces")]
    wet = [e["file"] for e in extras if e.get("category") == "outerwear" and e.get("waterproof")]
    print(f"\n{len(manifest)} photos in manifest ({len(manifest) - len(extras)} replace illustrations, {len(extras)} extra items).")
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
