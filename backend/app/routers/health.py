from fastapi import APIRouter

from app.integrations.health import check_all

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/apis")
def api_health() -> dict:
    """Preflight: key present plus one tiny real call to each API (no fallback)."""
    return check_all()
