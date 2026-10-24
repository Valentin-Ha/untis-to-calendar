import logging
from pathlib import Path

from .config import Config
from .core.untis_client import get_timetable_events
from .sinks import create_sinks, write_to_sinks


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    base_dir = Path(__file__).resolve().parent.parent.parent
    env_file = base_dir / ".env"

    config = Config.from_env(env_file)
    sinks = create_sinks(config, fallback="local")

    events, window_start, window_end = get_timetable_events(config)
    write_to_sinks(sinks, events, window_start, window_end)

    print(f"Stundenplan bis zum {window_end} als {config.mode or 'local'} exportiert.")


if __name__ == "__main__":
    main()
