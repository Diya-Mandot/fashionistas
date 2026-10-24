"""Check OPENAI_API_KEY without printing it: python check_key.py"""
from app.config import get_settings

key = get_settings().openai_api_key.strip()
if not key:
    raise SystemExit("OPENAI_API_KEY is empty in backend/.env")
print(f"Key loaded: {key[:7]}…{key[-4:]} ({len(key)} chars)")
