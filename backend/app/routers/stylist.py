from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StringConstraints, ValidationError
from sqlmodel import Session, select

from app.agent.runner import start_run, wait
from app.config import get_settings
from app.core.vision import InvalidImageError, ValidatedImage, validate_upload
from app.db import get_session
from app.integrations.anthropic_client import key_configured
from app.models import AgentRunRecord

router = APIRouter(prefix="/api/stylist", tags=["stylist"])


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    city: Optional[str] = None


class PlanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    home_city: Optional[str] = None
    location: Optional[Location] = None
    preferred_colors: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]] = Field(
        default_factory=list, max_length=12,
    )
    wait: bool = False


class PlanResponse(BaseModel):
    run_id: str
    status: str
    plan: Optional[dict[str, Any]] = None
    trace: list[dict[str, Any]] = Field(default_factory=list)
    mode: dict[str, Any]


def _mode() -> dict[str, Any]:
    s = get_settings()
    return {"agents": s.agents_mode, "decisions": s.decisions_mode, "key_configured": key_configured()}


def _create_plan(body: PlanRequest, session: Session, portrait: Optional[ValidatedImage] = None) -> PlanResponse:
    run_id = start_run(
        body.message.strip(), body.home_city, body.location.model_dump() if body.location else None,
        preferred_colors=tuple(body.preferred_colors),
        portrait=portrait,
    )
    if body.wait:
        wait(run_id)
    rec = session.get(AgentRunRecord, run_id)
    session.refresh(rec)
    return PlanResponse(run_id=run_id, status=rec.status, plan=rec.plan, trace=rec.trace, mode=_mode())


@router.post("/plan", response_model=PlanResponse)
def create_plan(body: PlanRequest, session: Session = Depends(get_session)):
    return _create_plan(body, session)


@router.post("/plan/photo", response_model=PlanResponse)
async def create_photo_plan(
    plan: Annotated[str, Form(max_length=6000)],
    photo: Annotated[UploadFile, File()],
    session: Session = Depends(get_session),
) -> PlanResponse:
    try:
        body = PlanRequest.model_validate_json(plan)
        portrait = await validate_upload(photo)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid stylist plan request.") from exc
    except InvalidImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    return await run_in_threadpool(_create_plan, body, session, portrait)


@router.get("/runs/{run_id}", response_model=AgentRunRecord)
def get_run(run_id: str, session: Session = Depends(get_session)):
    rec = session.get(AgentRunRecord, run_id)
    if not rec:
        raise HTTPException(404, "Run not found")
    return rec


@router.get("/runs", response_model=list[AgentRunRecord])
def list_runs(limit: int = 10, session: Session = Depends(get_session)):
    stmt = select(AgentRunRecord).order_by(AgentRunRecord.created_at.desc()).limit(min(limit, 50))
    return list(session.exec(stmt))
