from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.seed import reset

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/reset")
def reset_demo(session: Session = Depends(get_session)) -> dict:
    """Restore the seed closet and clear stylist runs between demo runs."""
    count = reset(session)
    warnings = []
    for path in get_settings().scan_uploads_dir.glob("scan_*.jpg"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            warnings.append("A scan image needs local cleanup.")
    return {"items": count, "warnings": list(dict.fromkeys(warnings))}
