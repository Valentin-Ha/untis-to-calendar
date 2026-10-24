import datetime
import hashlib

from dateutil import parser

from ..models import UntisEvent


def get_substitution_text(period) -> str | None:
    return (
        getattr(period, "substText", None)
        or getattr(period, "subst_text", None)
        or getattr(period, "substit_text", None)
        or getattr(period, "substitutionText", None)
    )


def get_period_summary(period) -> str:
    subjects = getattr(period, "subjects", None) or []
    if subjects:
        return subjects[0].long_name

    lstext = getattr(period, "lstext", None) or getattr(period, "ls_text", None)
    if lstext:
        return lstext

    return "Unbekannt"


def build_description(period) -> str | None:
    code = getattr(period, "code", None)
    substitution_text = get_substitution_text(period)

    if code == "cancelled":
        if substitution_text and substitution_text != "Unterricht":
            return substitution_text
        return "Diese Stunde wurde abgesagt."
    if code == "irregular":
        if substitution_text and substitution_text != "Unterricht":
            return substitution_text
        return "Diese Stunde ist irregulär."
    if substitution_text and substitution_text != "Unterricht":
        return substitution_text
    if code:
        return f"Geändert: {code}"
    return None


def build_uid(period, start: datetime.datetime, uid_suffix: str) -> str:
    """Stable UID for a period, so calendar backends can update instead of duplicate."""
    period_id = getattr(period, "id", None)
    if period_id is not None:
        return f"untis-{period_id}{uid_suffix}"

    # Ohne WebUntis-ID: Startzeit und Unterrichtsnummer bleiben auch bei Vertretungen gleich
    lsnumber = getattr(period, "lsnumber", None) or get_period_summary(period)
    key = f"{start.isoformat()}|{lsnumber}"
    return f"untis-x{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}{uid_suffix}"


def period_to_event(
    period,
    room_mapping: dict[int, str],
    tz: datetime.tzinfo,
    uid_suffix: str,
    irregular_as_cancelled: bool = False,
) -> UntisEvent:
    summary = get_period_summary(period)
    # WebUntis liefert lokale Zeiten ohne Zeitzone
    start = parser.parse(str(period.start))
    end = parser.parse(str(period.end))
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    if end.tzinfo is None:
        end = end.replace(tzinfo=tz)

    location = "Unbekannt"
    if period.rooms:
        room_id = period.rooms[0].id
        location = room_mapping.get(room_id, "Unbekannt")

    description = build_description(period)
    # "irregular" sind Vertretungen/verlegte Stunden, die meist stattfinden; nur auf Wunsch als Ausfall
    cancelled_codes = ("cancelled", "irregular") if irregular_as_cancelled else ("cancelled",)
    cancelled = getattr(period, "code", None) in cancelled_codes

    return UntisEvent(
        uid=build_uid(period, start, uid_suffix),
        summary=summary,
        start=start,
        end=end,
        location=location,
        description=description,
        cancelled=cancelled,
    )