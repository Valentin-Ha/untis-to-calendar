import hashlib
import os
from pathlib import Path
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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
    timezone: str = "Europe/Berlin"
    irregular_as_cancelled: bool = False

    # CalDAV
    caldav_url: str | None = None
    caldav_username: str | None = None
    caldav_password: str | None = None
    caldav_calendar: str = "Stundenplan"

    # Scheduler
    update_interval: int = 15  # Minuten

    @property
    def modes(self) -> list[str]:
        """Output modes from MODE, which may be a comma-separated list."""
        return [mode.strip().lower() for mode in self.mode.split(",") if mode.strip()]

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def uid_suffix(self) -> str:
        """Suffix shared by all event UIDs of this WebUntis account.

        Lets the CalDAV sink recognize its own events, even in a calendar
        that also holds other events or events of another account.
        """
        account = f"{self.school.strip()}|{self.username.strip()}".lower()
        digest = hashlib.sha256(account.encode("utf-8")).hexdigest()[:10]
        return f"-{digest}@untis-to-calendar"

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

        irregular_as_cancelled = _parse_bool(
            "IRREGULAR_AS_CANCELLED", get_env("IRREGULAR_AS_CANCELLED", None, required=False)
        )

        timezone = get_env("TIMEZONE", None, required=False) or "Europe/Berlin"
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError(
                f"TIMEZONE `{timezone}` ist keine gültige Zeitzone (z. B. `Europe/Berlin`)."
            ) from None

        return cls(
            server=get_env("SERVER", required=True),
            username=get_env("USERNAME", required=True),
            password=get_env("PASSWORD", required=True),
            school=get_env("SCHOOL", required=True),
            useragent=get_env("USERAGENT", None, required=False) or None,
            mode=get_env("MODE", "local", required=False),
            calendar_file=Path(calendar_file_str) if calendar_file_str else None,
            data_dir=Path(data_dir_str) if data_dir_str else None,
            timezone=timezone,
            irregular_as_cancelled=irregular_as_cancelled,
            caldav_url=get_env("CALDAV_URL", None, required=False) or None,
            caldav_username=get_env("CALDAV_USERNAME", None, required=False) or None,
            caldav_password=get_env("CALDAV_PASSWORD", None, required=False) or None,
            caldav_calendar=get_env("CALDAV_CALENDAR", None, required=False) or "Stundenplan",
            update_interval=update_interval,
        )


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("", "0", "false", "no", "nein", "off"):
        return False
    if normalized in ("1", "true", "yes", "ja", "on"):
        return True
    raise ValueError(f"{name} muss `true` oder `false` sein, nicht `{value}`.")


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
