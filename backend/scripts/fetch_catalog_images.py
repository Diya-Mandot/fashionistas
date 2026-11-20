"""Download the Shop Your Gaps catalog photos from Wikimedia Commons.

    cd backend && uv run python scripts/fetch_catalog_images.py [--force]

Each catalog.json entry names its Commons file in `source_file`. This script
downloads it, resizes it to at most 900px, saves catalog/images/<id>.jpg, and
writes `image` and `credit` (author, license, source URL) back into
catalog.json. It also regenerates catalog/CREDITS.md. Existing images are kept
unless --force is passed. Only freely licensed files (CC0, public domain,
CC BY, CC BY-SA) are accepted.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"
CATALOG = CATALOG_DIR / "catalog.json"
IMAGES = CATALOG_DIR / "images"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "fashionistas-catalog-script/0.1 (demo catalog builder)"}
FREE = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? [0-9.]+)", re.I)
MAX_SIDE = 900
THUMB_WIDTH = 960  # a standard Wikimedia thumbnail step; non-standard widths are throttled hard


def _get(url: str, **kw) -> requests.Response:
    """GET with a pause between calls and backoff on 429 (Commons rate-limits bursts)."""
    for attempt in range(6):
        time.sleep(1.5)
        r = requests.get(url, headers=UA, timeout=60, **kw)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        time.sleep(int(r.headers.get("Retry-After") or 0) or 20 * (attempt + 1))
    raise RuntimeError(f"Rate-limited by Commons: {url}")


def fetch_commons(title: str, dest: Path) -> dict[str, str]:
    """Download Commons file `title` to `dest` as a resized JPEG and return its credit."""
    r = _get(API, params={
        "action": "query", "format": "json", "titles": f"File:{title}", "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": THUMB_WIDTH,
    })
    page = next(iter(r.json()["query"]["pages"].values()))
    if "imageinfo" not in page:
        raise RuntimeError(f"Not found on Commons: {title}")
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    license_ = meta.get("LicenseShortName", {}).get("value", "")
    if not FREE.match(license_):
        raise RuntimeError(f"{title}: license {license_!r} is not free")
    author = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip() or "unknown"

    im = Image.open(io.BytesIO(_get(info.get("thumburl") or info["url"]).content))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="JPEG", quality=86)
    return {
        "author": " ".join(author.split()),
        "license": license_,
        "source_url": f"https://commons.wikimedia.org/wiki/File:{quote(title.replace(' ', '_'))}",
    }


def write_credits(items: list[dict]) -> None:
    rows = [
        f"| {i['id']}.jpg | {i['name']} | {i['credit']['author']} | {i['credit']['license']} | {i['credit']['source_url']} |"
        for i in items if i.get("credit")
    ]
    (CATALOG_DIR / "CREDITS.md").write_text(
        "# Catalog photo credits\n\n"
        "Photos for the mock Shop Your Gaps catalog come from Wikimedia Commons under the licenses below, "
        "resized for the demo. The stores and product names are fictional. Each entry in catalog.json "
        "also carries its `credit`. Rebuild with `uv run python scripts/fetch_catalog_images.py`.\n\n"
        "| File | Product | Author | License | Source |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    force = "--force" in sys.argv
    items = json.loads(CATALOG.read_text(encoding="utf-8"))
    failed = []
    for item in items:
        title = item.get("source_file")
        dest = IMAGES / f"{item['id']}.jpg"
        if not title:
            continue
        if dest.exists() and item.get("credit") and not force:
            continue
        try:
            item["credit"] = fetch_commons(title, dest)
            item["image"] = f"/media/catalog/{dest.name}"
            print(f"ok   {item['id']}  {title}", flush=True)
        except Exception as exc:  # keep going; report at the end
            failed.append(item["id"])
            print(f"FAIL {item['id']}  {exc}", flush=True)
        # Save after every item so an interrupted run keeps its progress.
        CATALOG.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_credits(items)
    print(f"{len(items) - len(failed)} ok, {len(failed)} failed {failed or ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
