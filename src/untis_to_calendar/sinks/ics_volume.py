import datetime
import logging
from pathlib import Path

from ..config import Config
from ..models import UntisEvent
from .base import CalendarSink
from .ical import build_calendar


logger = logging.getLogger(__name__)


class ICSVolumeSink(CalendarSink):
    """Export to ICS file in Docker volume / data directory."""

    def __init__(self, config: Config):
        self.config = config

    def write(
        self,
        events: list[UntisEvent],
        window_start: datetime.date,
        window_end: datetime.date,
    ) -> None:
        calendar = build_calendar(events)

        data_dir = self.config.data_dir or Path("/data")
        data_dir.mkdir(parents=True, exist_ok=True)
        calendar_file = data_dir / "stundenplan.ics"

        with calendar_file.open("wb") as f:
            f.write(calendar.to_ical())

        logger.info(f"Stundenplan als {calendar_file} exportiert.")
