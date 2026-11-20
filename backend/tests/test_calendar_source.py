from datetime import date

from app.config import get_settings
from app.services import calendar_source

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
DTSTART:20261027T190000Z
DTEND:20261027T210000Z
SUMMARY:Dinner with the Acme team
LOCATION:Canlis, Seattle
DESCRIPTION:Dress code: cocktail attire
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;VALUE=DATE:20261028
SUMMARY:Morning run club
RRULE:FREQ=WEEKLY;COUNT=3
END:VEVENT
END:VCALENDAR
"""


def test_reads_real_ics_with_recurrence_and_hints(tmp_path, monkeypatch):
    f = tmp_path / "cal.ics"
    f.write_text(ICS)
    calendar_source._cache.clear()
    monkeypatch.setattr(get_settings(), "calendar_ics_url", str(f))
    cal = calendar_source.events_between(date(2026, 10, 26), date(2026, 11, 10))
    assert cal.source == "ics" and cal.label == "Your calendar"
    names = [(e["date"], e["name"], e["dress_code_hint"]) for e in cal.events]
    assert ("2026-10-28", "Morning run club", "athletic") in names
    assert ("2026-11-04", "Morning run club", "athletic") in names  # weekly recurrence expanded
    dinner = next(e for e in cal.events if e["name"].startswith("Dinner"))
    assert dinner["dress_code_hint"] == "cocktail attire" and dinner["location"] == "Canlis, Seattle"
    assert dinner["start_time"] is not None


def test_broken_feed_returns_no_events(monkeypatch):
    calendar_source._cache.clear()
    monkeypatch.setattr(get_settings(), "calendar_ics_url", "/nonexistent/calendar.ics")
    cal = calendar_source.events_between(date(2026, 10, 24), date(2026, 10, 31), date(2026, 10, 24))
    assert cal.source == "none" and "Couldn't read your calendar" in cal.note
    assert cal.events == []


def test_no_events_when_not_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "calendar_ics_url", "")
    cal = calendar_source.events_between(date(2026, 10, 24), date(2026, 10, 31), date(2026, 10, 24))
    assert cal.source == "none" and cal.note is None and cal.events == []
