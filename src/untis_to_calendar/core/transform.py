import datetime
import hashlib
import logging

from dateutil import parser

from ..models import UntisEvent


logger = logging.getLogger(__name__)

# Bereits gemeldete unbekannte IDs, damit der Scheduler nicht bei jedem Lauf erneut warnt
_warned_unknown_ids: set[tuple[str, int]] = set()


# WebUntis meldet einen gestrichenen Raum mit ID 0; die ursprüngliche Raum-ID steht dann in "orgid"
NO_ROOM_ID = 0


def get_raw_entries(period, key: str) -> list[dict]:
    """Entries in the raw WebUntis period data, e.g. key "ro" (rooms) or "su" (subjects).

    Deliberately avoids ``period.rooms``/``period.subjects``: python-webuntis raises
    IndexError there as soon as one ID is missing from getRooms()/getSubjects().
    """
    data = getattr(period, "_data", None) or {}
    return [entry for entry in data.get(key) or [] if isinstance(entry, dict) and "id" in entry]


def get_raw_ids(period, key: str) -> list[int]:
    return [entry["id"] for entry in get_raw_entries(period, key)]


def format_room_name(short_name: str | None, long_name: str | None, room_name: str) -> str:
    """Room name as configured by ROOM_NAME ("short", "long" or "both"), falling back to the other name."""
    short_name = (short_name or "").strip()
    long_name = (long_name or "").strip()
    if room_name == "short":
        return short_name or long_name
    if room_name == "both":
        if short_name and long_name and short_name != long_name:
            return f"{short_name} ({long_name})"
        return short_name or long_name
    return long_name or short_name


def build_room_mapping(rooms, room_name: str) -> dict[int, str]:
    """Room ID -> display name; rooms without any name are left out and resolve to the fallback."""
    mapping = {}
    for room in rooms:
        name = format_room_name(getattr(room, "name", None), getattr(room, "long_name", None), room_name)
        if name:
            mapping[room.id] = name
    return mapping


def resolve_name(ids: list[int], mapping: dict[int, str], kind: str) -> str | None:
    """Name of the first ID found in mapping; warns once per unknown ID."""
    for item_id in ids:
        if item_id not in mapping and (kind, item_id) not in _warned_unknown_ids:
            _warned_unknown_ids.add((kind, item_id))
            logger.warning(f"Unbekannte {kind}-ID {item_id} in WebUntis-Stundenplan, nutze Fallback")
    return next((mapping[item_id] for item_id in ids if item_id in mapping), None)


def get_substitution_text(period) -> str | None:
    return (
        getattr(period, "substText", None)
        or getattr(period, "subst_text", None)
        or getattr(period, "substit_text", None)
        or getattr(period, "substitutionText", None)
    )


def build_location(period, room_mapping: dict[int, str]) -> str:
    """Event location: the assigned room, or a hint if the room was removed."""
    entries = get_raw_entries(period, "ro")
    assigned_ids = [entry["id"] for entry in entries if entry["id"] != NO_ROOM_ID]
    location = resolve_name(assigned_ids, room_mapping, "Raum")
    if location:
        return location

    removed = [entry for entry in entries if entry["id"] == NO_ROOM_ID]
    # Nur ohne zugewiesenen Raum; ein vorhandener, aber nicht auflösbarer Raum bleibt "Unbekannt"
    if removed and not assigned_ids:
        original = next(
            (room_mapping[entry["orgid"]] for entry in removed if entry.get("orgid") in room_mapping),
            None,
        )
        return f"Kein Raum (statt {original})" if original else "Kein Raum"

    return "Unbekannt"


def get_period_summary(period, subject_mapping: dict[int, str]) -> str:
    subject = resolve_name(get_raw_ids(period, "su"), subject_mapping, "Fach")
    if subject:
        return subject

    lstext = getattr(period, "lstext", None) or getattr(period, "ls_text", None)
    if lstext:
        return lstext

    return "Unbekannt"


def build_title(summary: str, period, subst_text_in_title: bool) -> str:
    """Event title: the subject, optionally followed by the substitution text."""
    if not subst_text_in_title:
        return summary
    substitution_text = (get_substitution_text(period) or "").strip()
    # Gleiche Regel wie in build_description; Text, der schon im Titel steht, nicht doppeln
    if not substitution_text or substitution_text == "Unterricht":
        return summary
    if substitution_text.casefold() in summary.casefold():
        return summary
    return f"{summary} – {substitution_text}"


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


def build_uid(period, start: datetime.datetime, uid_suffix: str, summary: str) -> str:
    """Stable UID for a period, so calendar backends can update instead of duplicate."""
    period_id = getattr(period, "id", None)
    if period_id is not None:
        return f"untis-{period_id}{uid_suffix}"

    # Ohne WebUntis-ID: Startzeit und Unterrichtsnummer bleiben auch bei Vertretungen gleich
    lsnumber = getattr(period, "lsnumber", None) or summary
    key = f"{start.isoformat()}|{lsnumber}"
    return f"untis-x{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}{uid_suffix}"


def period_to_event(
    period,
    room_mapping: dict[int, str],
    subject_mapping: dict[int, str],
    tz: datetime.tzinfo,
    uid_suffix: str,
    irregular_as_cancelled: bool = False,
    subst_text_in_title: bool = False,
) -> UntisEvent:
    summary = get_period_summary(period, subject_mapping)
    # WebUntis liefert lokale Zeiten ohne Zeitzone
    start = parser.parse(str(period.start))
    end = parser.parse(str(period.end))
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    if end.tzinfo is None:
        end = end.replace(tzinfo=tz)

    location = build_location(period, room_mapping)

    description = build_description(period)
    # "irregular" sind Vertretungen/verlegte Stunden, die meist stattfinden; nur auf Wunsch als Ausfall
    cancelled_codes = ("cancelled", "irregular") if irregular_as_cancelled else ("cancelled",)
    cancelled = getattr(period, "code", None) in cancelled_codes

    return UntisEvent(
        # UID aus dem reinen Fach, damit sie sich nicht ändert, sobald ein Vertretungstext auftaucht
        uid=build_uid(period, start, uid_suffix, summary),
        summary=build_title(summary, period, subst_text_in_title),
        start=start,
        end=end,
        location=location,
        description=description,
        cancelled=cancelled,
    )