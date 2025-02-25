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
        useragent=''
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
        # Füge den Namen des Faches als Titel hinzu
        event.add('summary', period.subjects[0].name if period.subjects else 'Unbekannt')
        event.add('dtstart', parser.parse(str(period.start)))
        event.add('dtend', parser.parse(str(period.end)))

        # Räume sicher abfragen
        try:
            rooms = period.rooms
        except IndexError:
            rooms = []
        room_name = next((room.name for room in rooms if getattr(room, 'name', None)), 'Unbekannt')
        event.add('location', room_name)

        # Falls die Stunde geändert wurde, Hinweis in der Beschreibung hinzufügen
        if hasattr(period, 'code') and period.code:
            event.add('description', f'Geändert: {period.code}')

        calendar.add_component(event)

    # ICS-Datei speichern
    with open('stundenplan.ics', 'wb') as f:
        f.write(calendar.to_ical())

    print(f'Stundenplan bis zum {max_future_date} als Kalender exportiert.')
