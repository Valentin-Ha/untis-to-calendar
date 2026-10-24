import datetime
from abc import ABC, abstractmethod

from ..models import UntisEvent


class SinkError(RuntimeError):
    """Expected sink failure whose details were already logged."""


class CalendarSink(ABC):
    """Abstract base class for calendar output backends."""

    @abstractmethod
    def write(
        self,
        events: list[UntisEvent],
        window_start: datetime.date,
        window_end: datetime.date,
    ) -> None:
        """Write events to the calendar backend.

        ``window_start`` to ``window_end`` (both inclusive) is the date range
        WebUntis was asked for. Syncing backends may treat events in that range
        that are missing from ``events`` as removed.
        """
        pass
