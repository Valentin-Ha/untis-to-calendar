import datetime
import logging
from pathlib import Path

import webuntis

from ..config import Config
from ..models import UntisEvent
from .transform import period_to_event


logger = logging.getLogger(__name__)


def parse_date(date_value) -> datetime.date:
    if isinstance(date_value, int):
        year = date_value // 10000
        month = (date_value % 10000) // 100
        day = date_value % 100
        return datetime.date(year, month, day)
    if isinstance(date_value, datetime.datetime):
        return date_value.date()
    if isinstance(date_value, datetime.date):
        return date_value
    raise TypeError("Unsupported date format")


def fetch_timetable(session, start_date: datetime.date) -> tuple[list, datetime.date]:
    timetable = []
    max_future_date = start_date

    for days_ahead in range(1, 20):
        end_date = start_date + datetime.timedelta(days=days_ahead)
        try:
            periods = session.my_timetable(start=start_date, end=end_date)
        except Exception as e:
            logger.warning(f"Abruf bis {end_date} fehlgeschlagen, nutze Daten bis {max_future_date}: {e}")
            break
        if periods:
            timetable = periods
            max_future_date = end_date

    return timetable, max_future_date


def periods_to_events(
    timetable,
    room_mapping: dict[int, str],
    subject_mapping: dict[int, str],
    config: Config,
) -> list[UntisEvent]:
    """Convert periods to events, skipping (with a warning) any period that fails to convert."""
    tz = config.tzinfo
    events = []
    seen_uids = set()
    for period in timetable:
        try:
            event = period_to_event(
                period,
                room_mapping,
                subject_mapping,
                tz,
                config.uid_suffix,
                config.irregular_as_cancelled,
                config.subst_text_in_title,
            )
        except Exception as e:
            data = getattr(period, "_data", None) or {}
            logger.warning(
                f"Stunde übersprungen (ID {data.get('id')}, Datum {data.get('date')}, "
                f"Beginn {data.get('startTime')}): {type(e).__name__}: {e}"
            )
            continue
        if event.uid in seen_uids:
            logger.debug(f"Doppelte Stunde übersprungen: {event.uid}")
            continue
        seen_uids.add(event.uid)
        events.append(event)
    return events


def get_timetable_events(config: Config) -> tuple[list[UntisEvent], datetime.date, datetime.date]:
    """Fetch the timetable and return its events plus the first and last day it covers."""
    with webuntis.Session(
        username=config.username,
        password=config.password,
        school=config.school,
        server=config.server,
        useragent=config.useragent or "",
    ) as s:
        try:
            s.login()
            logger.info("Login erfolgreich")
        except Exception as e:
            logger.error(f"Login fehlgeschlagen: {e}")
            logger.info(
                "Prüfpunkte: USERNAME/SCHOOL/SERVER in `.env`, keine Leerzeichen, exakte WebUntis-Daten."
            )
            raise

        schoolyears = s.schoolyears()
        current_schoolyear = next(
            (
                sy
                for sy in schoolyears
                if parse_date(sy.start) <= datetime.date.today() <= parse_date(sy.end)
            ),
            None,
        )

        if current_schoolyear:
            logger.info("Aktuelles Schuljahr gefunden.")
        else:
            logger.error("Kein aktuelles Schuljahr gefunden.")
            raise ValueError("Kein aktuelles Schuljahr gefunden. Bitte die WebUntis-Daten prüfen.")

        today = datetime.date.today()
        weekday = today.weekday()
        start_date = (
            today - datetime.timedelta(days=weekday)
            if weekday < 5
            else today + datetime.timedelta(days=(7 - weekday))
        )

        schoolyear_start = parse_date(current_schoolyear.start)
        if start_date < schoolyear_start:
            start_date = schoolyear_start

        timetable, max_future_date = fetch_timetable(s, start_date)

        room_mapping = {room.id: room.long_name for room in s.rooms()}
        subject_mapping = {subject.id: subject.long_name for subject in s.subjects()}

        events = periods_to_events(timetable, room_mapping, subject_mapping, config)

        return events, start_date, max_future_date