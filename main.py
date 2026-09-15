import datetime
import logging
import os
from pathlib import Path

import icalendar
from dateutil import parser
import webuntis


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / '.env'
CALENDAR_FILE = BASE_DIR / 'stundenplan.ics'


def load_env_file(file_path: Path) -> None:
    # - Key=Value
    # - Kommentare / Leerzeilen ignorieren
    if not file_path.exists():
        return

    with file_path.open('r', encoding='utf-8-sig') as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value


def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ValueError(f'{name} fehlt in `.env` oder den Umgebungsvariablen.')
    return value or ''

load_env_file(ENV_FILE)

# - WebUntis Zugang
SERVER = get_env('SERVER', required=True)
USERNAME = get_env('USERNAME', required=True)
PASSWORD = get_env('PASSWORD', required=True)
SCHOOL = get_env('SCHOOL', required=True)
USERAGENT = get_env('USERAGENT', '', required=False)

# - Ausgabe
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)


def parse_date(date_value):
    # - WebUntis liefert teils int, teils date/datetime
    if isinstance(date_value, int):
        year = date_value // 10000
        month = (date_value % 10000) // 100
        day = date_value % 100
        return datetime.date(year, month, day)
    if isinstance(date_value, datetime.datetime):
        return date_value.date()
    if isinstance(date_value, datetime.date):
        return date_value
    raise TypeError('Unsupported date format')


def get_substitution_text(period):
    # - mögliche Feldnamen in WebUntis
    return (
        getattr(period, 'substText', None)
        or getattr(period, 'subst_text', None)
        or getattr(period, 'substit_text', None)
        or getattr(period, 'substitutionText', None)
    )


def get_period_summary(period):
    # - Originalfach bevorzugen
    subjects = getattr(period, 'subjects', None) or []
    if subjects:
        return subjects[0].long_name

    lstext = getattr(period, 'lstext', None) or getattr(period, 'ls_text', None)
    if lstext:
        return lstext

    return 'Unbekannt'


def build_description(period):
    # - Zusatzinfo für Kalenderdetails
    code = getattr(period, 'code', None)
    substitution_text = get_substitution_text(period)

    if code == 'cancelled':
        if substitution_text and substitution_text != 'Unterricht':
            return substitution_text
        return 'Diese Stunde wurde abgesagt.'
    if code == 'irregular':
        if substitution_text and substitution_text != 'Unterricht':
            return substitution_text
        return 'Diese Stunde ist irregulär.'
    if substitution_text and substitution_text != 'Unterricht':
        return substitution_text
    if code:
        return f'Geändert: {code}'
    return None


def fetch_timetable(session, start_date):
    # - Zeitraum schrittweise erweitern, ohne bei leeren Tagen abzubrechen
    timetable = []
    max_future_date = start_date

    for days_ahead in range(1, 20):  # 20 Tage in die Zukunft
        end_date = start_date + datetime.timedelta(days=days_ahead)
        try:
            periods = session.my_timetable(start=start_date, end=end_date)
        except Exception:
            break
        if periods:
            timetable = periods
            max_future_date = end_date

    return timetable, max_future_date

with webuntis.Session(
        username=USERNAME,
        password=PASSWORD,
        school=SCHOOL,
        server=SERVER,
        useragent=USERAGENT,
) as s:
    try:
        s.login()
        logging.info('Login erfolgreich')
    except Exception as e:
        logging.error(f'Login fehlgeschlagen: {e}')
        logging.info('Prüfpunkte: USERNAME/SCHOOL/SERVER in `.env`, keine Leerzeichen, exakte WebUntis-Daten.')
        raise

    schoolyears = s.schoolyears()
    current_schoolyear = next(
        (sy for sy in schoolyears if parse_date(sy.start) <= datetime.date.today() <= parse_date(sy.end)),
        None,
    )

    if current_schoolyear:
        logging.info('Aktuelles Schuljahr gefunden.')
    else:
        logging.error('Kein aktuelles Schuljahr gefunden.')
        raise ValueError('Kein aktuelles Schuljahr gefunden. Bitte die WebUntis-Daten prüfen.')

    today = datetime.date.today()
    weekday = today.weekday()
    start_date = today - datetime.timedelta(days=weekday) if weekday < 5 else today + datetime.timedelta(days=(7 - weekday))

    schoolyear_start = parse_date(current_schoolyear.start)
    if start_date < schoolyear_start:
        start_date = schoolyear_start

    timetable, max_future_date = fetch_timetable(s, start_date)

    # - Raum-ID -> Klarname
    room_mapping = {room.id: room.long_name for room in s.rooms()}

    # - ICS Container
    calendar = icalendar.Calendar()
    calendar.add('prodid', '-//WebUntis Calendar Export//')
    calendar.add('version', '2.0')

    for period in timetable:
        event = icalendar.Event()

        event.add('summary', get_period_summary(period))

        event.add('dtstart', parser.parse(str(period.start)))
        event.add('dtend', parser.parse(str(period.end)))

        room_name = 'Unbekannt'
        if period.rooms:
            room_id = period.rooms[0].id
            room_name = room_mapping.get(room_id, 'Unbekannt')
        event.add('location', room_name)

        description = build_description(period)
        if description:
            event.add('description', description)

        if getattr(period, 'code', None) == 'cancelled' or getattr(period, 'code', None) == 'irregular':
            event.add('status', 'CANCELED')

        calendar.add_component(event)

    with CALENDAR_FILE.open('wb') as f:
        f.write(calendar.to_ical())

    print(f'Stundenplan bis zum {max_future_date} als Kalender exportiert.')
