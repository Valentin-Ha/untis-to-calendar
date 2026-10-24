"""Calendar output backends (sinks)."""

import datetime
import logging

from ..config import Config
from ..models import UntisEvent
from .base import CalendarSink, SinkError
from .caldav_sync import CalDAVSink
from .ics_local import ICSLocalSink
from .ics_volume import ICSVolumeSink


SINKS: dict[str, type[CalendarSink]] = {
    "local": ICSLocalSink,
    "docker": ICSVolumeSink,
    "caldav": CalDAVSink,
}

logger = logging.getLogger(__name__)


def create_sinks(config: Config, fallback: str) -> list[CalendarSink]:
    """Instantiate one sink per mode in MODE; unknown modes fall back to ``fallback``."""
    sink_classes: list[type[CalendarSink]] = []
    for mode in config.modes or [fallback]:
        sink_class = SINKS.get(mode)
        if sink_class is None:
            logger.warning(f"Unbekannter Modus `{mode}`, verwende `{fallback}`.")
            sink_class = SINKS[fallback]
        if sink_class not in sink_classes:
            sink_classes.append(sink_class)

    return [sink_class(config) for sink_class in sink_classes]


def write_to_sinks(
    sinks: list[CalendarSink],
    events: list[UntisEvent],
    window_start: datetime.date,
    window_end: datetime.date,
) -> None:
    """Write to every sink, even if one of them fails, then report the failures."""
    failed = []
    for sink in sinks:
        try:
            sink.write(events, window_start, window_end)
        except Exception as e:
            # Traceback nur bei unerwarteten Fehlern, SinkError hat seine Details schon geloggt
            logger.error(
                f"Ausgabe {type(sink).__name__} fehlgeschlagen: {e}",
                exc_info=not isinstance(e, SinkError),
            )
            failed.append(type(sink).__name__)

    if failed:
        raise SinkError(f"Ausgabe fehlgeschlagen: {', '.join(failed)}")
