import logging
from pathlib import Path

from .config import Config
from .core.untis_client import get_timetable_events
from .sinks.ics_local import ICSLocalSink
from .sinks.ics_volume import ICSVolumeSink


SINKS = {
    "local": ICSLocalSink,
    "docker": ICSVolumeSink,
}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    base_dir = Path(__file__).resolve().parent.parent.parent
    env_file = base_dir / ".env"

    config = Config.from_env(env_file)

    events, max_future_date = get_timetable_events(config)

    sink_class = SINKS.get(config.mode, ICSLocalSink)
    sink = sink_class(config)
    sink.write(events)

    print(f"Stundenplan bis zum {max_future_date} als {config.mode} exportiert.")


if __name__ == "__main__":
    main()