from abc import ABC, abstractmethod

from ..models import UntisEvent


class CalendarSink(ABC):
    """Abstract base class for calendar output backends."""

    @abstractmethod
    def write(self, events: list[UntisEvent]) -> None:
        """Write events to the calendar backend."""
        pass