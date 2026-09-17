import logging
from pathlib import Path

import icalendar

from ..config import Config
from ..models import UntisEvent
from .base import CalendarSink


logger = logging.getLogger(__name__)


class ICSVolumeSink(CalendarSink):
    """Export to ICS file in Docker volume / data directory."""

    def __init__(self, config: Config):
        self.config = config

    def write(self, events: list[UntisEvent]) -> None:
        calendar = icalendar.Calendar()
        calendar.add("prodid", "-//WebUntis Calendar Export//")
        calendar.add("version", "2.0")

        for event in events:
            ics_event = icalendar.Event()
            ics_event.add("summary", event.summary)
            ics_event.add("dtstart", event.start)
            ics_event.add("dtend", event.end)
            ics_event.add("location", event.location)
            if event.description:
                ics_event.add("description", event.description)
            if event.cancelled:
                ics_event.add("status", "CANCELED")
            calendar.add_component(ics_event)

        data_dir = self.config.data_dir or Path("/data")
        data_dir.mkdir(parents=True, exist_ok=True)
        calendar_file = data_dir / "stundenplan.ics"

        with calendar_file.open("wb") as f:
            f.write(calendar.to_ical())

        logger.info(f"Stundenplan als {calendar_file} exportiert.")