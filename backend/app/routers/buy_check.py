"""Should I Buy This?: photo -> attributes -> compatibility engine -> Claude judgment.

Nothing is added to the closet until the user taps "I bought it" (POST /keep).
Free users get FREE_CHECKS checks a month; the limit is enforced before any
Vision or Claude call.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import get_settings
from app.core import compatibility as compat
from app.core.vision import InvalidImageError
from app.db import get_session
from app.integrations.decisions_client import CandidateItem, EventIn, PurchaseRequest, judge_purchase
from app.models import AppFlag, BuyCheck, WardrobeItem, new_id
from app.services import calendar_source
from app.services.item_analysis import analyze_photo, scan_meta
from app.trace import Timer, TraceStep

router = APIRouter(prefix="/api/buy-check", tags=["buy-check"])

FREE_CHECKS = 3
PRO_FLAG = "pro"
# Dev override: only checks after this ISO timestamp count toward the free limit.
USAGE_RESET_FLAG = "buy_check_usage_reset_at"
NEW_ITEM_ID = "new"  # id of the not-yet-owned item inside top_outfits


class BuyCheckResponse(BaseModel):
    check_id: str
    item: dict[str, Any]
    result: dict[str, Any]
    trace: list[TraceStep]
    usage: dict[str, Any]


# ---------------------------------------------------------------------------
# Usage / Pro (mocked)
# ---------------------------------------------------------------------------
def is_pro(session: Session) -> bool:
    flag = session.get(AppFlag, PRO_FLAG)
    return bool(flag and flag.value == "1")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo


def checks_this_month(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    reset = session.get(AppFlag, USAGE_RESET_FLAG)
    if reset and reset.value:
        start = max(start, _aware(datetime.fromisoformat(reset.value)))
    count = 0
    for created in session.exec(select(BuyCheck.created_at)):
        count += _aware(created) >= start
    return count


def reset_usage(session: Session, now: datetime | None = None) -> None:
    """Dev override: start the free count over without deleting past checks."""
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    flag = session.get(AppFlag, USAGE_RESET_FLAG) or AppFlag(key=USAGE_RESET_FLAG)
    flag.value = stamp
    session.add(flag)
    session.commit()


def usage(session: Session) -> dict[str, Any]:
    return {"checks_used": checks_this_month(session), "limit": FREE_CHECKS, "pro": is_pro(session)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _uploads() -> Path:
    return Path(get_settings().uploads_dir)


def _compact(item: WardrobeItem | compat.Piece) -> CandidateItem:
    return CandidateItem(
        name=item.name or item.category, category=item.category, color=item.color, style=item.style,
        formality=item.formality, season=item.season, material=item.material, waterproof=item.waterproof,
    )


def _upcoming_events(today: date) -> list[dict[str, Any]]:
    try:
        return calendar_source.events_between(today, today + timedelta(days=compat.CALENDAR_WINDOW_DAYS)).events
    except Exception:  # a broken calendar must never break a buy check
        return []


def _response(check: BuyCheck, session: Session) -> BuyCheckResponse:
    item = {k: v for k, v in check.attrs.items() if k != "scan_meta"}
    return BuyCheckResponse(
        check_id=check.id, item=item, result=check.result,
        trace=[TraceStep(**s) for s in check.trace], usage=usage(session),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("", response_model=BuyCheckResponse)
async def buy_check(file: UploadFile = File(...), session: Session = Depends(get_session)):
    pro = is_pro(session)
    used = checks_this_month(session)
    if not pro and used >= FREE_CHECKS:
        return JSONResponse(status_code=402, content={"paywall": "buy_check", "used": used, "limit": FREE_CHECKS})

    try:
        analysis = await analyze_photo(file)
    except InvalidImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    cls, image, trace = analysis.classification, analysis.image, analysis.trace

    check_id = new_id("chk")
    suffix = Path(image.filename).suffix or ".jpg"
    pending = _uploads() / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / f"{check_id}{suffix}").write_bytes(image.content)

    attrs: dict[str, Any] = {
        "name": cls.name, "category": cls.category, "subcategory": cls.subcategory, "color": cls.color,
        "style": cls.style, "brand": analysis.signals.ocr_brand, "season": cls.season, "material": cls.material,
        "formality": cls.formality, "waterproof": cls.waterproof,
        "image_url": f"/media/uploads/pending/{check_id}{suffix}", "scan_meta": scan_meta(analysis),
    }

    # --- Compatibility engine (rules) -------------------------------------
    t = Timer()
    today = date.today()
    closet = sorted(session.exec(select(WardrobeItem)), key=lambda i: i.id)
    pieces = [compat.as_piece(i) for i in closet]
    new = compat.as_piece({**attrs, "id": NEW_ITEM_ID})
    events = _upcoming_events(today)
    a = compat.assess(new, pieces, events, today)
    trace.append(
        TraceStep(
            kind="tool_call",
            tool="compatibility",
            title=f"Rules: {compat.outfit_count_label(a.outfit_count)} outfits · "
                  f"{len(a.duplicates)} possible duplicate{'s' if len(a.duplicates) != 1 else ''} · "
                  f"baseline {a.score}",
            detail=(f"Fills: {', '.join(a.gaps_filled)}" if a.gaps_filled else "Fills no closet gap")
                   + f" · {len(a.calendar_matches)} upcoming event{'s' if len(a.calendar_matches) != 1 else ''}",
            result={
                "outfit_count": a.outfit_count, "gaps_filled": a.gaps_filled,
                "duplicates": [d.item.name for d in a.duplicates], "calendar_matches": a.calendar_matches,
                "baseline": a.score,
            },
            source="local",
            duration_ms=t.ms,
        )
    )

    # --- Claude judgment ----------------------------------------------------
    t = Timer()
    index = {p.id: n for n, p in enumerate(pieces)}
    outfits = [[index[p.id] for p in o.items if p.id != NEW_ITEM_ID] for o in a.candidates]
    req = PurchaseRequest(
        item=_compact(new), closet=[_compact(i) for i in closet], outfits=outfits,
        duplicates=[index[d.item.id] for d in a.duplicates], gaps=a.gaps_filled,
        events=[EventIn(name=m["event"], date=m["date"]) for m in a.calendar_matches],
        outfit_count=a.outfit_count, baseline=a.score,
    )
    j = judge_purchase(req)
    confirmed = set(j.duplicates)
    dups = [d for d in a.duplicates if index[d.item.id] in confirmed]
    rules_score = compat.baseline_score(a.outfit_count, bool(a.gaps_filled), len(a.calendar_matches), len(dups))
    score = max(0, min(100, rules_score + j.adjustment))
    verdict = compat.verdict(score)
    trace.append(
        TraceStep(
            kind="decision",
            tool="judge_purchase",
            title=f"Decisions: {verdict.replace('_', ' ').title()} · score {score}"
                  + (f" ({j.adjustment:+d})" if j.adjustment else ""),
            detail=j.score_reason + (f" · {j.meta.note}" if j.meta.note else ""),
            args=j.meta.request_preview,
            result=j.model_dump(exclude={"meta"}),
            source=j.meta.source,
            duration_ms=t.ms,
        )
    )

    by_id = {i.id: i for i in closet}
    new_row = WardrobeItem(id=NEW_ITEM_ID, source="buy_check", **{k: v for k, v in attrs.items() if k != "scan_meta"})
    top_outfits = [
        {
            "items": [(new_row if p.id == NEW_ITEM_ID else by_id[p.id]).model_dump(mode="json") for p in a.candidates[n].items],
            "includes_new": True,
        }
        for n in j.top_outfits
    ]
    result = {
        "score": score,
        "verdict": verdict,
        "outfit_count": a.outfit_count,
        "duplicates": [{"item_id": d.item.id, "name": d.item.name, "reason": d.reason} for d in dups],
        "gap_filled": j.gap_filled,
        "calendar_matches": a.calendar_matches,
        "est_wears_per_year": j.est_wears_per_year,
        "top_outfits": top_outfits,
        "score_reason": j.score_reason,
    }
    trace.append(TraceStep(kind="final", tool="buy_check", title=f"Verdict: {verdict.replace('_', ' ').title()}",
                           detail=j.score_reason, result={"check_id": check_id, "score": score}, source="local"))

    check = BuyCheck(
        id=check_id, attrs=attrs, result=result, trace=[s.model_dump(mode="json") for s in trace],
        image_path=str(pending / f"{check_id}{suffix}"),
    )
    session.add(check)
    session.commit()
    session.refresh(check)
    return _response(check, session)


@router.get("/{check_id}", response_model=BuyCheckResponse)
def get_buy_check(check_id: str, session: Session = Depends(get_session)):
    check = session.get(BuyCheck, check_id)
    if check is None:
        raise HTTPException(404, "Check not found")
    return _response(check, session)


@router.post("/{check_id}/keep")
def keep_buy_check(check_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    """I bought it: move the photo out of pending and add the item to the closet."""
    check = session.get(BuyCheck, check_id)
    if check is None:
        raise HTTPException(404, "Check not found")
    if check.kept:
        raise HTTPException(409, "Already added to your closet")

    item_id = new_id("itm")
    image_url = ""
    src = Path(check.image_path)
    if check.image_path and src.is_file():
        dest = _uploads() / f"{item_id}{src.suffix}"
        shutil.move(str(src), dest)
        image_url = f"/media/uploads/{dest.name}"
    attrs = {k: v for k, v in check.attrs.items() if k in WardrobeItem.model_fields and k != "image_url"}
    item = WardrobeItem(id=item_id, source="buy_check", image_url=image_url, **attrs)
    check.kept, check.item_id = True, item_id
    if image_url:  # point the stored result at the photo's new home (JSON columns need reassigning)
        check.attrs = {**check.attrs, "image_url": image_url}
        check.result = {
            **check.result,
            "top_outfits": [
                {**o, "items": [{**i, "image_url": image_url} if i.get("id") == NEW_ITEM_ID else i for i in o["items"]]}
                for o in check.result.get("top_outfits", [])
            ],
        }
    session.add(item)
    session.add(check)
    session.commit()
    session.refresh(item)
    return {"item": item.model_dump(mode="json")}
