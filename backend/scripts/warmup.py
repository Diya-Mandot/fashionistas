"""Warm-up before the demo: run every demo path LIVE once so honest replay
recordings exist if the network fails on stage.

    cd backend && uv run python scripts/warmup.py

Requires the backend to be running (make dev) and OPENAI_API_KEY in backend/.env.
"""

import sys
from io import BytesIO

import httpx
from PIL import Image

BASE = "http://localhost:8000"
PROMPTS = [
    "Packing for a tech conference in Seattle Tue–Thu. There's a fancy dinner Tuesday night and I want to look professional but a little edgy.",
    "Pack my bag for NYC this weekend: networking brunch and a Broadway show",
    "First day at a new job Monday, rainy, want to look put-together but not stiff",
]


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=300)
    pf = c.get("/api/health/apis").json()
    print("Preflight:", {k: pf[k] for k in ("decisions", "agents")})
    if not (pf["decisions"].get("ok") and pf["agents"].get("ok")):
        print("APIs are not green; fix the key/access first.")
        return 1
    for p in PROMPTS:
        r = c.post("/api/stylist/plan", json={"message": p, "wait": True}).json()
        run = c.get(f"/api/stylist/runs/{r['run_id']}").json()
        print(f"- {p[:50]}… -> {r['status']} · sources {run['sources']}")
    im = Image.new("RGB", (600, 700), (235, 232, 225))
    im.paste((40, 60, 90), (150, 120, 450, 600))
    buf = BytesIO()
    im.save(buf, format="JPEG")
    s = c.post("/api/closet/scan", files={"file": ("navy_rain_jacket.jpg", buf.getvalue(), "image/jpeg")}).json()
    print("- scan ->", s["item"]["name"], "·", [t["source"] for t in s["trace"]])
    c.delete(f"/api/closet/{s['item']['id']}")
    print("Done. Recordings are in backend/recordings/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
