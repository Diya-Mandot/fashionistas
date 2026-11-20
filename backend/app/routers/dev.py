from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.routers.buy_check import reset_usage, usage
from app.seed import reset

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/reset")
def reset_demo(session: Session = Depends(get_session)) -> dict:
    """Restore the seed closet and clear stylist runs between demo runs."""
    return {"items": reset(session)}


@router.post("/reset-buy-checks")
def reset_buy_checks(session: Session = Depends(get_session)) -> dict:
    """Testing override: give back the free Should I Buy checks. The limit still applies afterwards."""
    reset_usage(session)
    return usage(session)
