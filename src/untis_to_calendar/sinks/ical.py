"""iCalendar building shared by all sinks."""

import datetime
import hashlib

import icalendar

from ..models import UntisEvent


PRODID = "-//WebUntis Calendar Export//"
FINGERPRINT_PROPERTY = "X-UNTIS-FINGERPRINT"


def event_fingerprint(event: UntisEvent) -> str:
    """Hash over all event fields, used to detect changed events."""
    parts = [
        event.uid,
        event.summary,
        event.start.isoformat(),
        event.end.isoformat(),
        event.location,
        event.description or "",
        "cancelled" if event.cancelled else "",
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def build_vevent(event: UntisEvent) -> icalendar.Event:
    ics_event = icalendar.Event()
    ics_event.add("uid", event.uid)
    ics_event.add("dtstamp", datetime.datetime.now(datetime.timezone.utc))
    ics_event.add("summary", event.summary)
    ics_event.add("dtstart", event.start)
    ics_event.add("dtend", event.end)
    ics_event.add("location", event.location)
    if event.description:
        ics_event.add("description", event.description)
    if event.cancelled:
        ics_event.add("status", "CANCELLED")
    ics_event.add(FINGERPRINT_PROPERTY, event_fingerprint(event))
    return ics_event


def build_calendar(events: list[UntisEvent]) -> icalendar.Calendar:
    calendar = icalendar.Calendar()
    calendar.add("prodid", PRODID)
    calendar.add("version", "2.0")

    for event in events:
        calendar.add_component(build_vevent(event))

    # VTIMEZONE für alle verwendeten TZIDs, sonst ist die Datei laut RFC 5545 unvollständig.
    # Auf den Zeitraum der Events begrenzt, damit nicht alle Umstellungen seit 1970 drinstehen.
    if events:
        calendar.add_missing_timezones(
            first_date=min(event.start for event in events).date() - datetime.timedelta(days=1),
            last_date=max(event.end for event in events).date() + datetime.timedelta(days=1),
        )
    return calendar
