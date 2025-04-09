import webuntis
import datetime
from dateutil import parser
import uuid

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

    # Versuche bis zu 20 Tage in die Zukunft den Stundenplan abzufragen.
    for days_ahead in range(1, 20):
        try:
            end_date = start_date + datetime.timedelta(days=days_ahead)
            timetable = s.my_timetable(start=start_date, end=end_date)
            if len(timetable) > 0:
                max_future_date = end_date
            else:
                break
        except Exception:
            break

    # Statt ein ICS zu erstellen, erzeugen wir eine Liste von Dictionaries für jedes Event.
    timetable_events = []

    for period in timetable:
        # Bestimme den Fachnamen
        subject_name = period.subjects[0].name if period.subjects else 'Unbekannt'

        # Setze summary und ggf. description
        if period.code and period.code.lower() == 'cancelled':
            summary = f"Entfall: {subject_name}"
            description = None
        elif period.substText:
            summary = f"Ä: {subject_name}"
            description = f"Geändert: {period.substText}"
        else:
            summary = subject_name
            description = None

        # Parse der Start- und Endzeit
        dtstart_obj = parser.parse(str(period.start))
        dtend_obj = parser.parse(str(period.end))
        # Formatierung im typischen ICS-Format (UTC-Zeit). Passe dies ggf. an, falls du lokale Zeiten verwenden willst.
        dtstart = dtstart_obj.strftime('%Y%m%dT%H%M%SZ')
        dtend = dtend_obj.strftime('%Y%m%dT%H%M%SZ')

        # Räume ermitteln
        try:
            rooms = period.rooms
        except IndexError:
            rooms = []
        room_name = next((room.name for room in rooms if getattr(room, 'name', None)), 'Unbekannt')
        location = "Raum " + room_name

        # Eindeutige UID generieren. Hier kombinieren wir den Fachnamen, das Startdatum und eine zufällig erzeugte UUID.
        uid = f"{subject_name}-{dtstart}-{uuid.uuid4()}"

        event_dict = {
            'uid': uid,
            'summary': summary,
            'description': description,
            'dtstart': dtstart,
            'dtend': dtend,
            'location': location
        }

        timetable_events.append(event_dict)

    # Beispielsweise die erzeugten Dictionaries ausgeben oder weiterverarbeiten
    print("Exportierte Events:")
    for event in timetable_events:
        print(event)

    print(f'Stundenplan bis zum {max_future_date} exportiert.')
