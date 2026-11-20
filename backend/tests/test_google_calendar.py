import base64
import json
import time
from datetime import date
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from app.config import get_settings
from app.services import calendar_source, google_calendar as gc


def _id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).rstrip(b"=").decode()
    return f"x.{payload}.y"


@pytest.fixture()
def google(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "google_oauth_client_id", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_oauth_client_secret", "secret")
    monkeypatch.setattr(s, "google_token_file", str(tmp_path / "tok.json"))
    monkeypatch.setattr(s, "google_calendar_ids", "primary")
    monkeypatch.setattr(s, "calendar_ics_url", "")
    gc._events_cache.clear()
    gc._pending.clear()
    yield s


def _connect(token_body=None):
    """Run the consent redirect + code exchange against a mocked Google."""
    url = gc.authorization_url("http://localhost:5173/")
    q = parse_qs(urlsplit(url).query)
    assert q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
    assert gc.CALENDAR_SCOPE in q["scope"][0]
    verifier, back = gc.take_state(q["state"][0])
    body = token_body or {
        "access_token": "at1", "expires_in": 3600, "refresh_token": "rt1",
        "scope": f"openid {gc.CALENDAR_SCOPE} email", "id_token": _id_token("me@example.com"),
    }
    with respx.mock:
        respx.post(gc.TOKEN_URL).mock(return_value=httpx.Response(200, json=body))
        gc.exchange_code("code123", verifier)
    return back


EVENTS = {
    "items": [
        {"id": "a", "iCalUID": "a@g", "status": "confirmed", "summary": "Client pitch",
         "location": "Acme HQ, 1 Main St, Seattle, WA", "description": "Dress code: suits",
         "start": {"dateTime": "2026-11-23T17:00:00Z"}},
        {"id": "b", "status": "confirmed", "summary": "Yoga", "start": {"date": "2026-11-24"}},
        {"id": "c", "status": "cancelled", "summary": "Gone", "start": {"date": "2026-11-24"}},
        {"id": "d", "status": "confirmed", "summary": "Declined party", "start": {"date": "2026-11-25"},
         "attendees": [{"self": True, "responseStatus": "declined"}]},
        {"id": "e", "status": "confirmed", "eventType": "workingLocation", "summary": "Office", "start": {"date": "2026-11-25"}},
    ]
}


def test_connect_and_read_events(google):
    assert gc.status() == {"configured": True, "connected": False, "email": None}
    assert _connect() == "http://localhost:5173/"
    assert gc.status() == {"configured": True, "connected": True, "email": "me@example.com"}

    with respx.mock:
        route = respx.get(f"{gc.API_URL}/calendars/primary/events").mock(return_value=httpx.Response(200, json=EVENTS))
        cal = calendar_source.events_between(date(2026, 11, 20), date(2026, 11, 30))
        assert route.calls[0].request.headers["Authorization"] == "Bearer at1"
        assert route.calls[0].request.url.params["singleEvents"] == "true"
    assert cal.source == "google" and cal.label == "Your Google Calendar" and cal.note is None
    names = [e["name"] for e in cal.events]
    assert names == ["Client pitch", "Yoga"]  # cancelled, declined, working-location skipped
    pitch, yoga = cal.events
    assert pitch["dress_code_hint"] == "suits" and pitch["calendar"] == "real" and pitch["start_time"]
    assert yoga["start_time"] is None and yoga["dress_code_hint"] == "athletic" and yoga["id"] == "cal_02"


def test_expired_access_token_is_refreshed(google):
    _connect()
    tok = gc.load_token()
    tok["expires_at"] = time.time() - 10
    gc._save_token(tok)
    with respx.mock:
        refresh = respx.post(gc.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "at2", "expires_in": 3600}))
        api = respx.get(f"{gc.API_URL}/calendars/primary/events").mock(return_value=httpx.Response(200, json={"items": []}))
        gc.fetch_events(date(2026, 11, 20), date(2026, 11, 21))
    assert refresh.called and api.calls[0].request.headers["Authorization"] == "Bearer at2"
    assert gc.load_token()["refresh_token"] == "rt1"


def test_revoked_grant_disconnects_and_returns_no_events(google):
    _connect()
    tok = gc.load_token()
    tok["expires_at"] = 0
    gc._save_token(tok)
    with respx.mock:
        respx.post(gc.TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
        cal = calendar_source.events_between(date(2026, 10, 24), date(2026, 10, 31), date(2026, 10, 24))
    assert cal.source == "none" and "Reconnect" in cal.note and cal.events == []
    assert not gc.connected()


def test_api_error_returns_no_events(google):
    _connect()
    with respx.mock:
        respx.get(f"{gc.API_URL}/calendars/primary/events").mock(return_value=httpx.Response(500, json={"error": {"message": "boom"}}))
        cal = calendar_source.events_between(date(2026, 10, 24), date(2026, 10, 31), date(2026, 10, 24))
    assert cal.source == "none" and "Couldn't read your Google Calendar" in cal.note


def test_refuses_when_calendar_scope_unticked(google):
    with pytest.raises(gc.GoogleCalendarError, match="Calendar access"):
        _connect({"access_token": "a", "refresh_token": "r", "scope": "openid email"})
    assert not gc.connected()


def test_all_calendars_uses_selected_list(google, monkeypatch):
    monkeypatch.setattr(google, "google_calendar_ids", "all")
    _connect()
    cals = {"items": [{"id": "primary", "selected": True}, {"id": "en.usa#holiday@group.v.calendar.google.com", "selected": True},
                      {"id": "hidden@x", "selected": False}]}
    with respx.mock:
        respx.get(f"{gc.API_URL}/users/me/calendarList").mock(return_value=httpx.Response(200, json=cals))
        a = respx.get(f"{gc.API_URL}/calendars/primary/events").mock(return_value=httpx.Response(200, json={"items": []}))
        b = respx.get(url__regex=r".*/calendars/en\.usa%23holiday%40group\.v\.calendar\.google\.com/events").mock(
            return_value=httpx.Response(200, json={"items": []}))
        gc.fetch_events(date(2026, 11, 20), date(2026, 11, 21))
    assert a.called and b.called


def test_oauth_routes(client, google):
    assert client.get("/api/calendar/google/status").json()["configured"] is True

    res = client.get("/api/calendar/google/connect", params={"return_to": "http://localhost:5173/?x=1"}, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"].startswith(gc.AUTH_URL)
    state = parse_qs(urlsplit(res.headers["location"]).query)["state"][0]

    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="testserver").pass_through()
        mock.post(gc.TOKEN_URL).mock(return_value=httpx.Response(200, json={
            "access_token": "at", "expires_in": 3600, "refresh_token": "rt",
            "scope": gc.CALENDAR_SCOPE, "id_token": _id_token("you@example.com")}))
        cb = client.get("/api/calendar/google/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert cb.headers["location"] == "http://localhost:5173/?x=1&calendar=connected"
    assert client.get("/api/calendar/google/status").json()["email"] == "you@example.com"

    # replayed state is rejected
    again = client.get("/api/calendar/google/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert "calendar_error" in again.headers["location"]

    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="testserver").pass_through()
        mock.post(gc.REVOKE_URL).mock(return_value=httpx.Response(200))
        assert client.post("/api/calendar/google/disconnect").json()["connected"] is False


def test_connect_never_redirects_off_site(client, google):
    res = client.get("/api/calendar/google/connect", params={"return_to": "https://evil.example/"}, follow_redirects=False)
    state = parse_qs(urlsplit(res.headers["location"]).query)["state"][0]
    cb = client.get("/api/calendar/google/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False)
    assert cb.headers["location"].startswith(get_settings().frontend_origin)
    assert "cancelled" in cb.headers["location"]
