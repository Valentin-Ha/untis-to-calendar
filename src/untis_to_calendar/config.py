import os
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Configuration for untis-to-calendar."""

    # WebUntis
    server: str
    username: str
    password: str
    school: str
    useragent: str | None = None

    # Output
    mode: str = "local"
    calendar_file: Path | None = None
    data_dir: Path | None = None

    # Scheduler
    update_interval: int = 15  # Minuten

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Config":
        if env_file and env_file.exists():
            _load_env_file(env_file)

        def get_env(name: str, default: str | None = None, required: bool = False) -> str:
            value = os.getenv(name, default)
            if required and not value:
                raise ValueError(f"{name} fehlt in `.env` oder den Umgebungsvariablen.")
            return value or ""

        calendar_file_str = get_env("CALENDAR_FILE", None, required=False)
        data_dir_str = get_env("DATA_DIR", None, required=False)
        update_interval_str = get_env("UPDATE_INTERVAL", "15", required=False)

        try:
            update_interval = int(update_interval_str)
        except ValueError:
            update_interval = 15

        return cls(
            server=get_env("SERVER", required=True),
            username=get_env("USERNAME", required=True),
            password=get_env("PASSWORD", required=True),
            school=get_env("SCHOOL", required=True),
            useragent=get_env("USERAGENT", None, required=False) or None,
            mode=get_env("MODE", "local", required=False),
            calendar_file=Path(calendar_file_str) if calendar_file_str else None,
            data_dir=Path(data_dir_str) if data_dir_str else None,
            update_interval=update_interval,
        )


def _load_env_file(file_path: Path) -> None:
    if not file_path.exists():
        return

    with file_path.open("r", encoding="utf-8-sig") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value