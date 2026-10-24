from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.seed import reset

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/reset")
def reset_demo(session: Session = Depends(get_session)) -> dict:
    """Restore the seed closet and clear stylist runs between demo runs."""
    return {"items": reset(session)}
