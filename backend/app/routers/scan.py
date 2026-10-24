from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from sqlmodel import Session

from app.core.vision import InvalidPhoto
from app.db import get_session
from app.integrations.common import AdapterError
from app.services.scanning import ScanConflict, ScanResult, ScanService, ScanStorageError

router = APIRouter(prefix="/api/scan", tags=["scan"])


@lru_cache
def get_scan_service() -> ScanService:
    return ScanService()


@router.post("", response_model=ScanResult)
async def scan_photo(
    file: UploadFile,
    idempotency_key: Annotated[str | None, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")] = None,
    session: Session = Depends(get_session), service: ScanService = Depends(get_scan_service),
):
    try:
        # Read a bounded amount, regardless of the caller's Content-Type or filename.
        data = await file.read(service.settings.scan_max_image_bytes + 1)
        if len(data) > service.settings.scan_max_image_bytes:
            raise HTTPException(413, "The photo exceeds the upload size limit.")
        return await service.scan(data, session, request_key=idempotency_key)
    except InvalidPhoto as exc:
        raise HTTPException(422, str(exc)) from None
    except ScanConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except AdapterError as exc:
        raise HTTPException(502, str(exc)) from None
    except TimeoutError:
        raise HTTPException(504, "The scan timed out. No closet items were saved.") from None
    except ScanStorageError as exc:
        raise HTTPException(500, str(exc)) from None
    finally:
        await file.close()


@router.get("/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str, session: Session = Depends(get_session), service: ScanService = Depends(get_scan_service)):
    try:
        return service.get_scan(session, scan_id)
    except LookupError:
        raise HTTPException(404, "Scan not found.") from None


@router.post("/{scan_id}/undo", response_model=ScanResult)
def undo_scan(scan_id: str, session: Session = Depends(get_session), service: ScanService = Depends(get_scan_service)):
    try:
        return service.undo(session, scan_id)
    except LookupError:
        raise HTTPException(404, "Scan not found.") from None
    except ScanStorageError as exc:
        raise HTTPException(500, str(exc)) from None
