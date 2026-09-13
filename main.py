import webuntis
import datetime
import icalendar
from dateutil import parser
import logging


def read_secrets(file_path):
    secrets = {}
    with open(file_path, 'r') as file:
        for line in file:
            if line.startswith("USERNAME:"):
                secrets['USERNAME'] = line.split(":", 1)[1].strip()
            elif line.startswith("PASSWORD:"):
                secrets['PASSWORD'] = line.split(":", 1)[1].strip()
    return secrets


secrets = read_secrets('Secrets.txt')

# WebUntis-Konfiguration
SERVER = 'mese.webuntis.com'
USERNAME = secrets['USERNAME']
PASSWORD = secrets['PASSWORD']
SCHOOL = 'Musterschule'
useragent = ''

# Logging konfigurieren
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# WebUntis-Sitzung erstellen
logging.debug(f"Verwende Schule: {SCHOOL}, Server: {SERVER}")
with webuntis.Session(
        username=USERNAME,
        password=PASSWORD,
        school=SCHOOL,
        server=SERVER,
        useragent=''
) as s:
    try:
        s.login()
        logging.info("Login erfolgreich")
    except Exception as e:
        logging.error(f"Login fehlgeschlagen: {e}")
        raise

    schoolyears = s.schoolyears()
    logging.debug(f"Alle Schuljahre: {schoolyears}")

    def parse_date(date_value):
        if isinstance(date_value, int):
            year = date_value // 10000
            month = (date_value % 10000) // 100
            day = date_value % 100
            return datetime.date(year, month, day)
        elif isinstance(date_value, datetime.datetime):
            return date_value.date()
        else:
            raise TypeError("Unsupported date format")

    # Ensure startDate and endDate are converted to datetime.date
    current_schoolyear = next((sy for sy in schoolyears if parse_date(sy.start) <= datetime.date.today() <= parse_date(sy.end)), None)

    if current_schoolyear:
        logging.debug(f"Aktuelles Schuljahr: {current_schoolyear}")
    else:
        logging.error("Kein aktuelles Schuljahr gefunden.")
        raise ValueError("Kein aktuelles Schuljahr gefunden. Bitte überprüfen Sie die Daten im WebUntis-System.")

    today = datetime.date.today()
    weekday = today.weekday()

    if weekday < 5:  # Montag bis Freitag
        start_date = today - datetime.timedelta(days=weekday)
    else:  # Samstag oder Sonntag
        start_date = today + datetime.timedelta(days=(7 - weekday))

    max_future_date = start_date

    for days_ahead in range(1, 20):  # maximal 20 Tage in Zukunft
        try:
            end_date = start_date + datetime.timedelta(days=days_ahead)
            logging.debug(f"Berechne Enddatum: {end_date}")
            timetable = s.my_timetable(start=start_date, end=end_date)
            logging.debug(f"Rohdaten des Stundenplans: {timetable}")
            if len(timetable) > 0:
                max_future_date = end_date
            else:
                break
        except Exception:
            break

    # Räume vorab abrufen und eine Zuordnung erstellen
    room_mapping = {room.id: room.long_name for room in s.rooms()}

    # iCalendar-Kalender erstellen
    calendar = icalendar.Calendar()
    calendar.add('prodid', '-//WebUntis Calendar Export//')
    calendar.add('version', '2.0')

    for period in timetable:
        event = icalendar.Event()
        # Füge den Namen des Faches als Titel hinzu
        event.add('summary', period.subjects[0].long_name if period.subjects else 'Unbekannt')
        event.add('dtstart', parser.parse(str(period.start)))
        event.add('dtend', parser.parse(str(period.end)))

        # Räume sicher abfragen und longName zuordnen
        room_name = 'Unbekannt'
        if period.rooms:
            room_id = period.rooms[0].id
            room_name = room_mapping.get(room_id, 'Unbekannt')
        event.add('location', room_name)

        # Falls die Stunde geändert wurde, Hinweis in der Beschreibung hinzufügen
        if hasattr(period, 'code') and period.code:
            if period.code == 'cancelled':
                event.add('status', 'CANCELED')
                event.add('description', 'Diese Stunde wurde abgesagt.')
            else:
                event.add('description', f'Geändert: {period.code}')

        calendar.add_component(event)

    # ICS-Datei speichern
    with open('stundenplan.ics', 'wb') as f:
        f.write(calendar.to_ical())

    print(f'Stundenplan bis zum {max_future_date} als Kalender exportiert.')
