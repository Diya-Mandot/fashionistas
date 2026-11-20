"""Check ANTHROPIC_API_KEY without printing it: python check_key.py"""
from app.config import get_settings

key = get_settings().anthropic_api_key.strip()
if not key:
    raise SystemExit("ANTHROPIC_API_KEY is empty in backend/.env")
print(f"Key loaded: {key[:10]}…{key[-4:]} ({len(key)} chars)")
