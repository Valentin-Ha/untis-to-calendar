import logging
import signal
import time
from pathlib import Path
from datetime import datetime, timedelta

from .config import Config
from .core.untis_client import get_timetable_events
from .sinks import SinkError, create_sinks, write_to_sinks
from .sinks.ical import event_fingerprint


logger = logging.getLogger(__name__)

shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    logger.info(f"Signal {signum} empfangen. Shutdown wird eingeleitet...")
    shutdown_requested = True


def get_events_hash(events) -> int:
    """Einfacher Hash zum Erkennen von Änderungen."""
    return hash(tuple(event_fingerprint(event) for event in events))


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

    sinks = create_sinks(config, fallback="docker")

    # Für Change-Detection (nur fürs Log, geschrieben wird immer)
    last_hash = None

    interval_seconds = config.update_interval * 60
    logger.info(
        f"Scheduler gestartet. Intervall: {config.update_interval} Minuten. Modus: {config.mode or 'docker'}"
    )

    run_count = 0
    while not shutdown_requested:
        run_count += 1
        try:
            logger.info(f"Run #{run_count}: Hole Stundenplan...")
            events, window_start, window_end = get_timetable_events(config)
            write_to_sinks(sinks, events, window_start, window_end)

            current_hash = get_events_hash(events)
            if current_hash != last_hash:
                logger.info("Stundenplan hat sich geändert. Calendar-App wird aktualisiert.")
                last_hash = current_hash
            else:
                logger.debug("Keine Änderungen am Stundenplan.")

            next_run = (datetime.now() + timedelta(seconds=interval_seconds)).strftime("%Y-%m-%d %H:%M")
            logger.info(f"Nächster Lauf um {next_run} (in {config.update_interval} Minuten).")

        except SinkError as e:
            logger.error(f"Fehler im Scheduler-Lauf: {e}")
            logger.info(f"Nächster Versuch in {config.update_interval} Minuten.")
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