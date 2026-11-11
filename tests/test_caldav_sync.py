import datetime
import logging
from zoneinfo import ZoneInfo

import pytest
from caldav.lib.error import AuthorizationError, DAVError, RateLimitError

from untis_to_calendar.config import Config
from untis_to_calendar.models import UntisEvent
from untis_to_calendar.sinks import SinkError, caldav_sync, write_to_sinks
from untis_to_calendar.sinks.caldav_sync import CalDAVSink


TZ = ZoneInfo("Europe/Berlin")
WINDOW_START = datetime.date(2025, 1, 13)
WINDOW_END = datetime.date(2025, 1, 17)


def make_config() -> Config:
    return Config(
        server="example.webuntis.com",
        username="user",
        password="pw",
        school="schule",
        mode="caldav",
        caldav_url="https://caldav.example.com",
        caldav_username="user",
        caldav_password="pw",
    )


def make_events(config: Config) -> list[UntisEvent]:
    start = datetime.datetime(2025, 1, 13, 8, 0, tzinfo=TZ)
    return [
        UntisEvent(
            uid=f"1{config.uid_suffix}",
            summary="Mathematik",
            start=start,
            end=start + datetime.timedelta(minutes=45),
            location="Raum 101",
        )
    ]


class FailingClient:
    """Stands in for caldav.DAVClient; principal() raises the given error."""

    def __init__(self, error: Exception):
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def principal(self):
        raise self.error


@pytest.fixture
def failing_client(monkeypatch):
    def install(error: Exception) -> None:
        monkeypatch.setattr(caldav_sync.caldav, "DAVClient", lambda **kwargs: FailingClient(error))

    return install


def test_rate_limit_becomes_sink_error(failing_client):
    failing_client(
        RateLimitError(url="https://caldav.example.com", retry_after="3600", retry_after_seconds=3600.0, status=429)
    )
    config = make_config()

    with pytest.raises(SinkError, match=r"begrenzt gerade die Anfragen \(Rate Limit, Wartezeit laut Server: 3600 s\)") as exc_info:
        CalDAVSink(config).write(make_events(config), WINDOW_START, WINDOW_END)

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__


def test_rate_limit_without_retry_after(failing_client):
    failing_client(RateLimitError(url="https://caldav.example.com", status=503))
    config = make_config()

    with pytest.raises(SinkError, match=r"\(Rate Limit\)\. Nächster Versuch"):
        CalDAVSink(config).write(make_events(config), WINDOW_START, WINDOW_END)


def test_authorization_error_becomes_sink_error(failing_client):
    failing_client(AuthorizationError(url="https://caldav.example.com", reason="Unauthorized", status=401))
    config = make_config()

    with pytest.raises(SinkError, match="Anmeldung abgelehnt.*CALDAV_PASSWORD"):
        CalDAVSink(config).write(make_events(config), WINDOW_START, WINDOW_END)


def test_connection_error_becomes_sink_error(failing_client):
    failing_client(ConnectionError("connection refused"))
    config = make_config()

    with pytest.raises(SinkError, match="nicht erreichbar"):
        CalDAVSink(config).write(make_events(config), WINDOW_START, WINDOW_END)


def test_unexpected_error_is_not_wrapped(failing_client):
    failing_client(KeyError("bug"))
    config = make_config()

    with pytest.raises(KeyError):
        CalDAVSink(config).write(make_events(config), WINDOW_START, WINDOW_END)


def test_other_dav_error_is_not_wrapped(failing_client):
    failing_client(DAVError(url="https://caldav.example.com", reason="Internal Server Error", status=500))
    config = make_config()

    with pytest.raises(DAVError) as exc_info:
        CalDAVSink(config).write(make_events(config), WINDOW_START, WINDOW_END)

    assert not isinstance(exc_info.value, SinkError)


def test_write_to_sinks_logs_rate_limit_without_traceback(failing_client, caplog):
    failing_client(RateLimitError(url="https://caldav.example.com", retry_after_seconds=60.0, status=429))
    config = make_config()

    with caplog.at_level(logging.ERROR), pytest.raises(SinkError):
        write_to_sinks([CalDAVSink(config)], make_events(config), WINDOW_START, WINDOW_END)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors
    assert not any(r.exc_info for r in errors)
    assert "Traceback" not in caplog.text
    assert "Rate Limit, Wartezeit laut Server: 60 s" in caplog.text
