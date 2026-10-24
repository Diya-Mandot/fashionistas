"""Check OPENAI_API_KEY without printing it, then make one real call to each API.

    uv run python check_key.py
"""
import json

from app.config import get_settings
from app.integrations.health import check_all

key = get_settings().openai_api_key.strip()
if not key:
    raise SystemExit("OPENAI_API_KEY is empty in backend/.env")
print(f"Key loaded: {key[:7]}…{key[-4:]} ({len(key)} chars)")

report = check_all()
for check in report["checks"]:
    status = "OK  " if check["ok"] else "FAIL"
    detail = {k: v for k, v in check.items() if k not in ("api", "ok")}
    print(f"[{status}] {check['api']}: {json.dumps(detail)}")
raise SystemExit(0 if report["ok"] else 1)
