import datetime
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


def period_to_event(period, room_mapping: dict[int, str]) -> UntisEvent:
    summary = get_period_summary(period)
    start = parser.parse(str(period.start))
    end = parser.parse(str(period.end))

    location = "Unbekannt"
    if period.rooms:
        room_id = period.rooms[0].id
        location = room_mapping.get(room_id, "Unbekannt")

    description = build_description(period)
    cancelled = getattr(period, "code", None) in ("cancelled", "irregular")

    return UntisEvent(
        summary=summary,
        start=start,
        end=end,
        location=location,
        description=description,
        cancelled=cancelled,
    )