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
        except Exception:
            break
        if periods:
            timetable = periods
            max_future_date = end_date

    return timetable, max_future_date


def get_timetable_events(config: Config) -> tuple[list[UntisEvent], datetime.date]:
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

        events = [
            period_to_event(period, room_mapping)
            for period in timetable
        ]

        return events, max_future_date