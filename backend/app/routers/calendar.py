from datetime import date, timedelta
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.services import google_calendar
from app.services.calendar_source import events_between

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
def get_calendar(start: Optional[date] = None, end: Optional[date] = None, refresh: bool = False) -> dict:
    """Your Google Calendar / iCal feed, or the demo calendar, for a date range. refresh=true skips the cache."""
    start = start or date.today()
    end = end or start + timedelta(days=30)
    cal = events_between(start, end, refresh=refresh)
    return {"source": cal.source, "label": cal.label, "note": cal.note, "events": cal.events}


# ---------- Google Calendar OAuth ----------

def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}".lower()


def _safe_return(return_to: Optional[str]) -> str:
    """Only send the browser back to this app (dev frontend or the backend-served build): no open redirects."""
    s = get_settings()
    allowed = {_origin(s.frontend_origin), _origin(s.google_oauth_redirect_uri)}
    if return_to and _origin(return_to) in allowed and urlsplit(return_to).scheme in ("http", "https"):
        return return_to
    return s.frontend_origin.rstrip("/") + "/"


def _back(return_to: str, **params: str) -> RedirectResponse:
    p = urlsplit(return_to)
    query = [(k, v) for k, v in parse_qsl(p.query) if k not in ("calendar", "calendar_error")]
    query += list(params.items())
    return RedirectResponse(urlunsplit((p.scheme, p.netloc, p.path or "/", urlencode(query), "")), status_code=303)


@router.get("/google/status")
def google_status() -> dict:
    return google_calendar.status()


@router.get("/google/connect")
def google_connect(return_to: Optional[str] = None) -> RedirectResponse:
    """Browser navigates here; we bounce it to Google's consent screen."""
    back = _safe_return(return_to)
    if not google_calendar.oauth_configured():
        return _back(back, calendar_error="Google Calendar isn't set up on the server yet (missing OAuth client ID/secret)")
    return RedirectResponse(google_calendar.authorization_url(back), status_code=303)


@router.get("/google/callback")
def google_callback(state: str = "", code: Optional[str] = None, error: Optional[str] = None) -> RedirectResponse:
    pending = google_calendar.take_state(state)
    if pending is None:
        return _back(_safe_return(None), calendar_error="That sign-in link expired. Try connecting again")
    verifier, back = pending
    if error or not code:
        msg = "You cancelled the Google sign-in" if error == "access_denied" else f"Google sign-in failed ({error or 'no code'})"
        return _back(back, calendar_error=msg)
    try:
        google_calendar.exchange_code(code, verifier)
    except google_calendar.GoogleCalendarError as exc:
        return _back(back, calendar_error=str(exc))
    except Exception as exc:  # network trouble etc.
        return _back(back, calendar_error=f"Couldn't reach Google ({type(exc).__name__})")
    return _back(back, calendar="connected")


@router.post("/google/disconnect")
def google_disconnect() -> dict:
    google_calendar.disconnect()
    return google_calendar.status()
