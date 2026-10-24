import datetime
import logging

import caldav
from caldav.lib.error import DAVError, NotFoundError, UidConflictError

from ..config import Config
from ..models import UntisEvent
from .base import CalendarSink, SinkError
from .ical import FINGERPRINT_PROPERTY, build_calendar, event_fingerprint


logger = logging.getLogger(__name__)


class CalDAVSink(CalendarSink):
    """Sync events into a calendar on a CalDAV server.

    Only events whose UID carries this account's suffix are touched, and only
    inside the fetched date window, so lessons before it stay as history and
    other events in the same calendar are left alone.
    """

    def __init__(self, config: Config):
        if not config.caldav_url:
            raise ValueError(
                "CALDAV_URL fehlt in `.env` oder den Umgebungsvariablen (benötigt für MODE=caldav)."
            )
        self.config = config

    def write(
        self,
        events: list[UntisEvent],
        window_start: datetime.date,
        window_end: datetime.date,
    ) -> None:
        if not events:
            # Kann auch ein stiller Fehler beim Abruf sein, daher lieber nichts löschen
            logger.warning("Keine Stunden von WebUntis erhalten. Im CalDAV-Kalender wird nichts geändert.")
            return

        tz = self.config.tzinfo
        range_start = datetime.datetime.combine(window_start, datetime.time.min, tzinfo=tz)
        range_end = datetime.datetime.combine(
            window_end + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz
        )

        with caldav.DAVClient(
            url=self.config.caldav_url,
            username=self.config.caldav_username,
            password=self.config.caldav_password,
            timeout=60,
        ) as client:
            calendar = self._open_calendar(client)
            existing, duplicates = self._load_own_events(calendar, range_start, range_end)

            created = updated = unchanged = deleted = 0
            failures: list[str] = []

            for event in events:
                obj = existing.pop(event.uid, None)
                try:
                    if obj is None:
                        self._create(calendar, event)
                        created += 1
                    elif _stored_fingerprint(obj) != event_fingerprint(event):
                        _replace(obj, event)
                        updated += 1
                    else:
                        unchanged += 1
                except DAVError as e:
                    logger.error(f"CalDAV: Stunde {event.uid} konnte nicht gespeichert werden: {e}")
                    failures.append(event.uid)

            # Was jetzt noch übrig ist, gibt es in WebUntis nicht mehr
            for obj in list(existing.values()) + duplicates:
                try:
                    obj.delete()
                    deleted += 1
                except DAVError as e:
                    logger.error(f"CalDAV: Stunde {obj.url} konnte nicht gelöscht werden: {e}")
                    failures.append(str(obj.url))

        logger.info(
            f"CalDAV-Kalender „{self.config.caldav_calendar}“ synchronisiert: "
            f"{created} neu, {updated} geändert, {deleted} gelöscht, {unchanged} unverändert."
        )
        if failures:
            raise SinkError(f"CalDAV: {len(failures)} Änderung(en) fehlgeschlagen.")

    def _open_calendar(self, client: caldav.DAVClient) -> caldav.Calendar:
        name = self.config.caldav_calendar
        principal = client.principal()
        try:
            return principal.calendar(name=name)
        except NotFoundError:
            logger.info(f"CalDAV-Kalender „{name}“ nicht gefunden, wird angelegt.")
            return principal.make_calendar(name=name)

    def _load_own_events(
        self,
        calendar: caldav.Calendar,
        range_start: datetime.datetime,
        range_end: datetime.datetime,
    ) -> tuple[dict[str, caldav.Event], list[caldav.Event]]:
        """Return this account's events in the window by UID, plus extra copies of the same UID."""
        own: dict[str, caldav.Event] = {}
        duplicates: list[caldav.Event] = []

        for obj in calendar.search(start=range_start, end=range_end, event=True, expand=False):
            component = obj.icalendar_component
            uid = str(component.get("uid", ""))
            if not uid.endswith(self.config.uid_suffix):
                continue

            # Nie außerhalb des abgefragten Zeitraums löschen, auch wenn der Server mehr liefert
            dtstart = component.decoded("dtstart", None)
            if not isinstance(dtstart, datetime.datetime) or dtstart.tzinfo is None:
                continue
            if not range_start <= dtstart < range_end:
                continue

            if uid in own:
                duplicates.append(obj)
            else:
                own[uid] = obj

        return own, duplicates

    def _create(self, calendar: caldav.Calendar, event: UntisEvent) -> None:
        data = build_calendar([event]).to_ical().decode("utf-8")
        try:
            calendar.add_event(data)
        except UidConflictError:
            # Gleiche UID liegt schon unter anderer URL, z. B. von einem anderen Client angelegt
            _replace(calendar.event_by_uid(event.uid), event)


def _stored_fingerprint(obj: caldav.Event) -> str | None:
    value = obj.icalendar_component.get(FINGERPRINT_PROPERTY)
    return str(value) if value is not None else None


def _replace(obj: caldav.Event, event: UntisEvent) -> None:
    obj.data = build_calendar([event]).to_ical().decode("utf-8")
    obj.save()
