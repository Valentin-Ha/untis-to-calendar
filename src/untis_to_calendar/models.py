from dataclasses import dataclass
import datetime


@dataclass(frozen=True)
class UntisEvent:
    """Normalized calendar event from WebUntis."""

    uid: str
    summary: str
    start: datetime.datetime
    end: datetime.datetime
    location: str
    description: str | None = None
    cancelled: bool = False
