"""Google Calendar sync over OAuth 2.0 (authorization code + PKCE, offline access).

Flow: GET /api/calendar/google/connect -> Google consent screen -> GET /api/calendar/google/callback
exchanges the code for a refresh token, stored in GOOGLE_TOKEN_FILE (git-ignored folder). Events are
then read live from the Calendar API (read-only scope) and refreshed every couple of minutes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlencode

import httpx

from app.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API_URL = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
SCOPES = f"openid email {CALENDAR_SCOPE}"

STATE_TTL_S = 10 * 60
EVENTS_TTL_S = 2 * 60
SKIP_EVENT_TYPES = {"workingLocation", "outOfOffice", "focusTime"}

_lock = threading.RLock()
_pending: dict[str, tuple[float, str, str]] = {}  # state -> (created_at, pkce_verifier, return_to)
_events_cache: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}


class GoogleCalendarError(Exception):
    """A readable problem with the Google connection (shown to the user)."""


class NotConnected(GoogleCalendarError):
    pass


# ---------- configuration & token storage ----------

def oauth_configured() -> bool:
    s = get_settings()
    return bool(s.google_oauth_client_id.strip() and s.google_oauth_client_secret.strip())


def _token_path() -> Path:
    return Path(get_settings().google_token_file).expanduser()


def load_token() -> Optional[dict[str, Any]]:
    try:
        tok = json.loads(_token_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return tok if isinstance(tok, dict) and tok.get("refresh_token") else None


def _save_token(tok: dict[str, Any]) -> None:
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(tok, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def _delete_token() -> None:
    try:
        _token_path().unlink()
    except FileNotFoundError:
        pass
    _events_cache.clear()


def connected() -> bool:
    return oauth_configured() and load_token() is not None


def status() -> dict[str, Any]:
    tok = load_token() if oauth_configured() else None
    return {"configured": oauth_configured(), "connected": tok is not None, "email": (tok or {}).get("email")}


# ---------- OAuth flow ----------

def authorization_url(return_to: str) -> str:
    if not oauth_configured():
        raise GoogleCalendarError("Google Calendar isn't set up (missing GOOGLE_OAUTH_CLIENT_ID/SECRET)")
    s = get_settings()
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v[0] > STATE_TTL_S]:
            del _pending[k]
        _pending[state] = (now, verifier, return_to)
    params = {
        "client_id": s.google_oauth_client_id.strip(),
        "redirect_uri": s.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",  # gives us a refresh token
        "prompt": "consent",  # always return a refresh token, even on reconnect
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def take_state(state: str) -> Optional[tuple[str, str]]:
    """One-time use: returns (pkce_verifier, return_to) for a state we issued, else None."""
    with _lock:
        entry = _pending.pop(state, None)
    if not entry or time.time() - entry[0] > STATE_TTL_S:
        return None
    return entry[1], entry[2]


def _email_from_id_token(id_token: Optional[str]) -> Optional[str]:
    # Received directly from Google's token endpoint over TLS, so reading the claims is enough here.
    try:
        payload = id_token.split(".")[1]  # type: ignore[union-attr]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("email")
    except Exception:
        return None


def _google_error(res: httpx.Response) -> str:
    try:
        body = res.json()
    except ValueError:
        return f"HTTP {res.status_code}"
    err = body.get("error")
    if isinstance(err, dict):  # Calendar API style
        return str(err.get("message") or err.get("status") or res.status_code)
    return str(body.get("error_description") or err or res.status_code)


def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    s = get_settings()
    res = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": s.google_oauth_client_id.strip(),
            "client_secret": s.google_oauth_client_secret.strip(),
            "redirect_uri": s.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        timeout=10.0,
    )
    if res.status_code != 200:
        raise GoogleCalendarError(f"Google rejected the sign-in: {_google_error(res)}")
    data = res.json()
    if CALENDAR_SCOPE not in str(data.get("scope", "")).split():
        raise GoogleCalendarError("Calendar access wasn't granted. Tick the calendar box on Google's consent screen.")
    refresh = data.get("refresh_token") or (load_token() or {}).get("refresh_token")
    if not refresh:
        raise GoogleCalendarError("Google didn't return a refresh token; remove the app's access in your Google account and try again")
    tok = {
        "refresh_token": refresh,
        "access_token": data.get("access_token"),
        "expires_at": time.time() + int(data.get("expires_in", 3600)) - 60,
        "email": _email_from_id_token(data.get("id_token")),
        "scope": data.get("scope"),
        "connected_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        _save_token(tok)
        _events_cache.clear()
    return {"email": tok["email"]}


def disconnect() -> None:
    tok = load_token()
    if tok:
        try:  # best effort: also revoke the grant at Google
            httpx.post(REVOKE_URL, data={"token": tok["refresh_token"]}, timeout=5.0)
        except httpx.HTTPError:
            pass
    with _lock:
        _delete_token()


def _access_token(force_refresh: bool = False) -> str:
    with _lock:
        tok = load_token()
        if not tok:
            raise NotConnected("Google Calendar isn't connected")
        if not force_refresh and tok.get("access_token") and float(tok.get("expires_at", 0)) > time.time():
            return str(tok["access_token"])
        s = get_settings()
        res = httpx.post(
            TOKEN_URL,
            data={
                "client_id": s.google_oauth_client_id.strip(),
                "client_secret": s.google_oauth_client_secret.strip(),
                "refresh_token": tok["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
        if res.status_code in (400, 401) and "invalid_grant" in res.text:
            _delete_token()
            raise NotConnected("Google Calendar access expired or was revoked. Reconnect it")
        if res.status_code != 200:
            raise GoogleCalendarError(f"Couldn't refresh Google access: {_google_error(res)}")
        data = res.json()
        tok["access_token"] = data["access_token"]
        tok["expires_at"] = time.time() + int(data.get("expires_in", 3600)) - 60
        if data.get("refresh_token"):
            tok["refresh_token"] = data["refresh_token"]
        _save_token(tok)
        return str(tok["access_token"])


# ---------- Calendar API ----------

def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(2):
        token = _access_token(force_refresh=attempt > 0)
        res = httpx.get(f"{API_URL}{path}", params=params, headers={"Authorization": f"Bearer {token}"}, timeout=8.0)
        if res.status_code == 401 and attempt == 0:
            continue  # stale access token: refresh once and retry
        if res.status_code != 200:
            raise GoogleCalendarError(f"Google Calendar API error: {_google_error(res)}")
        return res.json()
    raise GoogleCalendarError("Google Calendar rejected our access token")


def _paged(path: str, params: dict[str, Any], max_pages: int = 10) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = None
    for _ in range(max_pages):
        data = _get(path, {**params, **({"pageToken": page_token} if page_token else {})})
        items.extend(data.get("items", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return items


def _calendar_ids() -> list[str]:
    raw = get_settings().google_calendar_ids.strip()
    if raw.lower() in ("all", "selected"):
        cals = _paged("/users/me/calendarList", {"minAccessRole": "reader", "maxResults": 250})
        return [c["id"] for c in cals if c.get("selected") and not c.get("hidden") and not c.get("deleted")] or ["primary"]
    return [p.strip() for p in raw.split(",") if p.strip()] or ["primary"]


def _normalize(ev: dict[str, Any]) -> Optional[dict[str, Any]]:
    if ev.get("status") == "cancelled" or ev.get("eventType") in SKIP_EVENT_TYPES:
        return None
    if any(a.get("self") and a.get("responseStatus") == "declined" for a in ev.get("attendees", [])):
        return None
    start = ev.get("start") or {}
    if start.get("dateTime"):
        dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone()
        day, time_str = dt.date(), dt.strftime("%H:%M")
    elif start.get("date"):
        day, time_str = date.fromisoformat(start["date"]), None
    else:
        return None
    return {
        "date": day,
        "start_time": time_str,
        "name": str(ev.get("summary") or "Busy"),
        "location": str(ev.get("location") or ""),
        "description": str(ev.get("description") or ""),
        "uid": ev.get("iCalUID") or ev.get("id"),
    }


def fetch_events(start: date, end: date, force: bool = False) -> list[dict[str, Any]]:
    """Raw events whose start falls in [start, end], across the configured calendars."""
    key = (start, end, get_settings().google_calendar_ids)
    hit = _events_cache.get(key)
    if hit and not force and time.time() - hit[0] < EVENTS_TTL_S:
        return [dict(e) for e in hit[1]]
    time_min = datetime.combine(start, dtime.min).astimezone().isoformat()
    time_max = datetime.combine(end + timedelta(days=1), dtime.min).astimezone().isoformat()
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for cal_id in _calendar_ids():
        items = _paged(
            f"/calendars/{quote(cal_id, safe='')}/events",
            {"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime", "maxResults": 250},
        )
        for item in items:
            ev = _normalize(item)
            if not ev or not (start <= ev["date"] <= end):
                continue
            dedupe = (ev["uid"], ev["date"], ev["start_time"])
            if dedupe in seen:
                continue
            seen.add(dedupe)
            out.append(ev)
    _events_cache[key] = (time.time(), out)
    return [dict(e) for e in out]
