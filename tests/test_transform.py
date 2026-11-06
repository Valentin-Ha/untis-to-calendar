import datetime
import logging
from zoneinfo import ZoneInfo

import pytest

from untis_to_calendar.config import Config
from untis_to_calendar.core import transform
from untis_to_calendar.core.transform import period_to_event
from untis_to_calendar.core.untis_client import periods_to_events


TZ = ZoneInfo("Europe/Berlin")
ROOMS = {1: "Raum 101"}
SUBJECTS = {10: "Mathematik"}


class FakePeriod:
    """Mimics webuntis.objects.PeriodObject: raw data in _data, lookups that blow up like the library's."""

    def __init__(self, period_id, rooms=(1,), subjects=(10,), date=20261109, start_time=800):
        self._data = {
            "id": period_id,
            "date": date,
            "startTime": start_time,
            "ro": [{"id": room_id} for room_id in rooms],
            "su": [{"id": subject_id} for subject_id in subjects],
        }
        self.id = period_id
        day = datetime.datetime.strptime(str(date), "%Y%m%d")
        self.start = day.replace(hour=start_time // 100, minute=start_time % 100)
        self.end = self.start + datetime.timedelta(minutes=45)
        self.code = None
        self.lstext = None

    @property
    def rooms(self):
        # python-webuntis: rooms(from_cache=True).filter(id=[...]) -> [0] auf leerem Ergebnis
        raise IndexError("list index out of range")

    @property
    def subjects(self):
        raise IndexError("list index out of range")


@pytest.fixture(autouse=True)
def reset_warned_ids():
    transform._warned_unknown_ids.clear()


def make_config() -> Config:
    return Config(server="example.webuntis.com", username="user", password="pw", school="schule")


def test_unknown_room_falls_back_to_unbekannt(caplog):
    period = FakePeriod(42, rooms=(999,))

    with caplog.at_level(logging.WARNING):
        event = period_to_event(period, ROOMS, SUBJECTS, TZ, "@test")

    assert event.location == "Unbekannt"
    assert event.summary == "Mathematik"
    assert event.start.tzinfo is TZ
    assert "999" in caplog.text


def test_known_room_and_subject_resolved_from_raw_data():
    event = period_to_event(FakePeriod(42), ROOMS, SUBJECTS, TZ, "@test")

    assert event.location == "Raum 101"
    assert event.summary == "Mathematik"
    assert event.uid == "untis-42@test"


def test_unknown_subject_falls_back_to_lstext():
    period = FakePeriod(42, subjects=(555,))
    period.lstext = "AG Robotik"

    assert period_to_event(period, ROOMS, SUBJECTS, TZ, "@test").summary == "AG Robotik"
    period.lstext = None
    assert period_to_event(period, ROOMS, SUBJECTS, TZ, "@test").summary == "Unbekannt"


def test_unknown_id_warned_only_once(caplog):
    with caplog.at_level(logging.WARNING):
        period_to_event(FakePeriod(1, rooms=(999,)), ROOMS, SUBJECTS, TZ, "@test")
        period_to_event(FakePeriod(2, rooms=(999,)), ROOMS, SUBJECTS, TZ, "@test")

    assert caplog.text.count("999") == 1


def test_missing_raw_keys():
    period = FakePeriod(42)
    del period._data["ro"]
    del period._data["su"]

    event = period_to_event(period, ROOMS, SUBJECTS, TZ, "@test")

    assert event.location == "Unbekannt"
    assert event.summary == "Unbekannt"


def test_broken_period_does_not_stop_others(caplog):
    broken = FakePeriod(2, start_time=900)
    broken.start = "kein Datum"
    timetable = [FakePeriod(1), broken, FakePeriod(3, rooms=(999,), start_time=1000)]

    config = make_config()

    with caplog.at_level(logging.WARNING):
        events = periods_to_events(timetable, ROOMS, SUBJECTS, config)

    assert [event.uid for event in events] == [f"untis-1{config.uid_suffix}", f"untis-3{config.uid_suffix}"]
    assert events[1].location == "Unbekannt"
    assert "Stunde übersprungen (ID 2, Datum 20261109" in caplog.text


def test_subst_text_in_title_when_enabled():
    period = FakePeriod(42)
    period.substText = "D-Klausur"

    event = period_to_event(period, ROOMS, SUBJECTS, TZ, "@test", subst_text_in_title=True)

    assert event.summary == "Mathematik – D-Klausur"
    assert event.description == "D-Klausur"


def test_subst_text_not_in_title_when_disabled():
    period = FakePeriod(42)
    period.substText = "D-Klausur"

    assert period_to_event(period, ROOMS, SUBJECTS, TZ, "@test").summary == "Mathematik"


@pytest.mark.parametrize("text", [None, "", "  ", "Unterricht", "Mathematik", "mathe"])
def test_subst_text_not_appended(text):
    period = FakePeriod(42)
    period.substText = text

    event = period_to_event(period, ROOMS, SUBJECTS, TZ, "@test", subst_text_in_title=True)

    assert event.summary == "Mathematik"


def test_subst_text_in_title_for_cancelled_period():
    period = FakePeriod(42)
    period.substText = "Exkursion"
    period.code = "cancelled"

    event = period_to_event(period, ROOMS, SUBJECTS, TZ, "@test", subst_text_in_title=True)

    assert event.summary == "Mathematik – Exkursion"
    assert event.cancelled


def test_fallback_uid_ignores_subst_text():
    without_text = FakePeriod(None)
    with_text = FakePeriod(None)
    with_text.substText = "D-Klausur"

    uid_without = period_to_event(without_text, ROOMS, SUBJECTS, TZ, "@test", subst_text_in_title=True).uid
    uid_with = period_to_event(with_text, ROOMS, SUBJECTS, TZ, "@test", subst_text_in_title=True).uid

    assert uid_without.startswith("untis-x")
    assert uid_without == uid_with


def test_config_reads_subst_text_in_title(monkeypatch):
    for name in ("SUBST_TEXT_IN_TITLE", "IRREGULAR_AS_CANCELLED", "TIMEZONE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (("SERVER", "s"), ("USERNAME", "u"), ("PASSWORD", "p"), ("SCHOOL", "x")):
        monkeypatch.setenv(name, value)

    assert Config.from_env().subst_text_in_title is False
    monkeypatch.setenv("SUBST_TEXT_IN_TITLE", "true")
    assert Config.from_env().subst_text_in_title is True
