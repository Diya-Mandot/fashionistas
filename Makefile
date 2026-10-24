.PHONY: dev backend frontend install test preflight warmup reset import-photos

install:
	cd backend && uv sync
	cd frontend && npm install

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# Runs both; Ctrl+C stops both.
dev:
	@trap 'kill 0' INT TERM; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

test:
	cd backend && uv run pytest -q

# One tiny real call to each API (needs OPENAI_API_KEY and the backend running).
preflight:
	@curl -s localhost:8000/api/health/apis | python3 -m json.tool

# Run every demo path live once so honest replay recordings exist.
warmup:
	cd backend && uv run python scripts/warmup.py

# Restore the seed closet and clear runs.
reset:
	@curl -s -X POST localhost:8000/api/dev/reset; echo

# Import a folder of real clothing photos: make import-photos DIR=~/Desktop/closet-photos
import-photos:
	cd backend && uv run python scripts/import_photos.py "$(DIR)"
