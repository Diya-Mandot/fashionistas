"""Pull live inventory from the Utah thrift stores into catalog/thrift.json.

    cd backend && uv run python scripts/sync_thrift.py

Reads each store's public Shopify feed (see app/services/thrift_feed.py),
keeps in-stock adult clothing, and rewrites thrift.json in one go. Sold items
drop out on the next sync. If a store can't be reached, its previous entries
are kept so one flaky site never empties the shop. Photos stay on the stores'
CDN; nothing is downloaded. The running server picks up the new file on its
next Shop request.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.catalog import THRIFT_PATH  # noqa: E402
from app.services.thrift_feed import STORES, USER_AGENT, build_catalog, fetch_store  # noqa: E402


def main() -> int:
    previous: list[dict] = []
    if THRIFT_PATH.exists():
        try:
            previous = json.loads(THRIFT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = []

    fetched, kept = [], []
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=30, follow_redirects=True) as client:
        for store in STORES:
            try:
                raw = fetch_store(store, client)
            except (httpx.HTTPError, ValueError) as e:
                old = [p for p in previous if p.get("store") == store.name]
                print(f"  {store.name}: fetch failed ({e}); keeping {len(old)} previous items", file=sys.stderr)
                kept.extend(old)
                continue
            fetched.append((store, raw))
            print(f"  {store.name}: {len(raw)} listings")

    catalog = sorted(build_catalog(fetched) + kept, key=lambda e: e["id"])
    if not catalog:
        print("No items fetched; leaving thrift.json unchanged.", file=sys.stderr)
        return 1
    THRIFT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = THRIFT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(THRIFT_PATH)

    by = Counter((p["store"], p["category"]) for p in catalog)
    print(f"Wrote {len(catalog)} items to {THRIFT_PATH} at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    for (store, category), n in sorted(by.items()):
        print(f"  {store:<24} {category:<12} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
