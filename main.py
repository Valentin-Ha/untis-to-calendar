import webuntis
import datetime
import icalendar
from dateutil import parser


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
SERVER = 'hepta.webuntis.com'
USERNAME = secrets['USERNAME']
PASSWORD = secrets['PASSWORD']
SCHOOL = 'Musterschule'
useragent = ''

# WebUntis-Sitzung erstellen
with webuntis.Session(
        username=USERNAME,
        password=PASSWORD,
        school=SCHOOL,
        server=SERVER,
        useragent=useragent
) as s:
    s.login()

    schoolyears = s.schoolyears()
    current_schoolyear = schoolyears[0]

    today = datetime.date.today()
    weekday = today.weekday()

    if weekday < 5:  # Montag bis Freitag
        start_date = today - datetime.timedelta(days=weekday)
    else:  # Samstag oder Sonntag
        start_date = today + datetime.timedelta(days=(7 - weekday))

    max_future_date = start_date

    start_date = datetime.date(2025, 2, 17)
    end_date = datetime.date(2025, 2, 21)

    for days_ahead in range(1, 20):  # maximal 20 Tage in Zukunft
        try:
            end_date = start_date + datetime.timedelta(days=days_ahead)
            timetable = s.my_timetable(start=start_date, end=end_date)
            if len(timetable) > 0:
                max_future_date = end_date
            else:
                break
        except Exception:
            break

    # iCalendar-Kalender erstellen
    calendar = icalendar.Calendar()
    calendar.add('prodid', '-//WebUntis Calendar Export//')
    calendar.add('version', '2.0')

    for period in timetable:
        event = icalendar.Event()
        # Den Namen des Fachs ermitteln
        subject_name = period.subjects[0].name if period.subjects else 'Unbekannt'

        # Wenn ein Änderungs-Code gesetzt ist und genau "cancelled" (ohne Beachtung der Groß-/Kleinschreibung),
        # wird der Eventtitel angepasst.
        if period.code and period.code.lower() == 'cancelled':
            event.add('summary', f"Entfall: {subject_name}")
        else:
            # Standardtitel: Fachname
            event.add('summary', subject_name)
            # Falls ein Änderungs-Code vorhanden ist (aber nicht 'cancelled'),
            # den Änderungs-Text in die Beschreibung schreiben.
            if period.substText:
                desc = f"Geändert: {period.substText}"
                event.add('description', desc)

        event.add('dtstart', parser.parse(str(period.start)))
        event.add('dtend', parser.parse(str(period.end)))

        # Räume sicher abfragen
        try:
            rooms = period.rooms
        except IndexError:
            rooms = []
        room_name = next((room.name for room in rooms if getattr(room, 'name', None)), 'Unbekannt')
        event.add('location', "Raum " + room_name)

        calendar.add_component(event)

    # ICS-Datei speichern
    with open('stundenplan.ics', 'wb') as f:
        f.write(calendar.to_ical())

    print(f'Stundenplan bis zum {max_future_date} als Kalender exportiert.')
