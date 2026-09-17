import logging
import signal
import time
from pathlib import Path
from datetime import datetime

from .config import Config
from .core.untis_client import get_timetable_events
from .sinks.ics_local import ICSLocalSink
from .sinks.ics_volume import ICSVolumeSink


SINKS = {
    "local": ICSLocalSink,
    "docker": ICSVolumeSink,
}

logger = logging.getLogger(__name__)

shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    logger.info(f"Signal {signum} empfangen. Shutdown wird eingeleitet...")
    shutdown_requested = True


def get_file_hash(file_path: Path) -> str | None:
    """Einfacher Hash zum Erkennen von Änderungen."""
    if not file_path.exists():
        return None
    with file_path.open("rb") as f:
        return hash(f.read())


def run_scheduler() -> None:
    global shutdown_requested

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    base_dir = Path(__file__).resolve().parent.parent.parent
    env_file = base_dir / ".env"

    config = Config.from_env(env_file)

    sink_class = SINKS.get(config.mode, ICSVolumeSink)
    sink = sink_class(config)

    # Für Change-Detection (optional)
    last_hash = None
    calendar_file = None
    if config.mode == "docker":
        data_dir = config.data_dir or Path("/data")
        calendar_file = data_dir / "stundenplan.ics"
    elif config.calendar_file:
        calendar_file = config.calendar_file

    interval_seconds = config.update_interval * 60
    logger.info(f"Scheduler gestartet. Intervall: {config.update_interval} Minuten. Modus: {config.mode}")

    run_count = 0
    while not shutdown_requested:
        run_count += 1
        try:
            logger.info(f"Run #{run_count}: Hole Stundenplan...")
            events, max_future_date = get_timetable_events(config)
            sink.write(events)

            # Change Detection (optional)
            if calendar_file:
                current_hash = get_file_hash(calendar_file)
                if current_hash != last_hash:
                    logger.info("Stundenplan hat sich geändert. Calendar-App wird aktualisiert.")
                    last_hash = current_hash
                else:
                    logger.debug("Keine Änderungen am Stundenplan.")

            next_run = datetime.now().strftime("%Y-%m-%d %H:%M")
            logger.info(f"Nächster Lauf um {next_run} (in {config.update_interval} Minuten).")

        except Exception as e:
            logger.error(f"Fehler im Scheduler-Lauf: {e}", exc_info=True)
            logger.info(f"Nächster Versuch in {config.update_interval} Minuten.")

        # Sleep in kleinen Schritten für schnelleren Shutdown
        for _ in range(interval_seconds):
            if shutdown_requested:
                break
            time.sleep(1)

    logger.info("Scheduler wurde ordnungsgemäß beendet.")


if __name__ == "__main__":
    run_scheduler()