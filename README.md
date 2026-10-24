# untis-to-calendar

Exportiert den eigenen Stundenplan aus **WebUntis** als `.ics`-Kalenderdatei oder synchronisiert ihn direkt in einen **CalDAV**-Kalender (Nextcloud, iCloud, Radicale, Baïkal …).

Das Tool kann einmalig per CLI laufen oder als Dienst (z. B. im Docker-Container), der den Stundenplan in einem festen Intervall neu abruft.

## Features

- Login bei WebUntis mit den eigenen Zugangsdaten
- Export ab dem Montag der aktuellen Woche (am Wochenende ab dem nächsten Montag), soweit WebUntis Daten liefert (max. ~3 Wochen im Voraus)
- Termine mit Fach, Raum und Zeit, mit fester Zeitzone (`TIMEZONE`) und UID pro Stunde
- Ausfälle werden als `STATUS:CANCELLED` markiert. Vertretungen und irreguläre Stunden bleiben normale Termine (oder auf Wunsch ebenfalls Ausfall, siehe `IRREGULAR_AS_CANCELLED`), der Vertretungstext landet in der Beschreibung
- **CalDAV-Sync**: neue Stunden werden angelegt, geänderte aktualisiert, Stunden, die WebUntis nicht mehr liefert, gelöscht. Pro Lauf werden nur geänderte Termine geschrieben.
- Mehrere Ausgaben gleichzeitig, z. B. `.ics`-Datei im Docker-Volume **und** CalDAV (`MODE=docker,caldav`)
- Scheduler mit konfigurierbarem Update-Intervall und sauberem Shutdown (SIGTERM/SIGINT)
- Erweiterbar über austauschbare Ausgabe-Backends („Sinks“)

## Voraussetzungen

- Python **3.10+** oder Docker
- Ein WebUntis-Account (Schüler-/Lehrer-Login)
- Für CalDAV: ein Kalender-Server mit CalDAV-Zugang

## Konfiguration

Alle Einstellungen kommen aus einer `.env`-Datei im Projektverzeichnis oder aus Umgebungsvariablen.

```bash
cp .env.example .env
```

| Variable          | Pflicht | Standard               | Beschreibung |
|-------------------|:-------:|------------------------|--------------|
| `SERVER`          | ja      | –                      | WebUntis-Server, z. B. `mese.webuntis.com` (steht in der URL beim Login im Browser) |
| `SCHOOL`          | ja      | –                      | Schulname, wie er in WebUntis verwendet wird (URL-Parameter `school=`) |
| `USERNAME`        | ja      | –                      | WebUntis-Benutzername |
| `PASSWORD`        | ja      | –                      | WebUntis-Passwort |
| `USERAGENT`       | nein    | leer                   | Eigener User-Agent für die API-Anfragen |
| `MODE`            | nein    | `local`                | Ausgabe-Modus: `local`, `docker`, `caldav` oder mehrere mit Komma, z. B. `docker,caldav` (siehe unten) |
| `CALENDAR_FILE`   | nein    | `./stundenplan.ics`    | Zieldatei im Modus `local` |
| `DATA_DIR`        | nein    | `/data`                | Zielverzeichnis im Modus `docker`; die Datei heißt immer `stundenplan.ics` |
| `TIMEZONE`        | nein    | `Europe/Berlin`        | Zeitzone, in der WebUntis die Stundenzeiten liefert |
| `IRREGULAR_AS_CANCELLED` | nein | `false`         | `true`: Stunden mit WebUntis-Code „irregulär“ (Vertretung, verlegte Stunde, Sonderveranstaltung) ebenfalls als Ausfall (`STATUS:CANCELLED`) markieren. Achtung: Diese Stunden finden meist statt. |
| `CALDAV_URL`      | für `caldav` | –                 | Adresse des CalDAV-Servers (siehe [CalDAV](#caldav)) |
| `CALDAV_USERNAME` | für `caldav` | –                 | Benutzername beim CalDAV-Server |
| `CALDAV_PASSWORD` | für `caldav` | –                 | Passwort bzw. App-Passwort beim CalDAV-Server |
| `CALDAV_CALENDAR` | nein    | `Stundenplan`          | Anzeigename des Zielkalenders; wird angelegt, falls er fehlt |
| `UPDATE_INTERVAL` | nein    | `15`                   | Abruf-Intervall des Schedulers in Minuten |

> **Hinweis:** `.env` enthält deine Passwörter und ist per `.gitignore` von Git ausgeschlossen. Nicht committen.
>
> Werte mit `$`, `#` oder Leerzeichen in einfache Anführungszeichen setzen, z. B. `CALDAV_PASSWORD='ab$cd'`. Docker Compose ersetzt sonst `$…` durch andere Variablen und schneidet ` #…` ab.
>
> Werte aus der `.env` haben Vorrang vor bereits gesetzten Umgebungsvariablen.

### Ausgabe-Modi

| Modus    | Ziel                               | Gedacht für |
|----------|------------------------------------|-------------|
| `local`  | `CALENDAR_FILE`                    | Lokale Ausführung per CLI |
| `docker` | `DATA_DIR/stundenplan.ics`         | Container mit gemountetem Volume |
| `caldav` | Kalender `CALDAV_CALENDAR` auf `CALDAV_URL` | Direkter Sync auf alle Geräte |

Mehrere Modi lassen sich mit Komma kombinieren. Schlägt eine Ausgabe fehl (z. B. CalDAV-Server nicht erreichbar), werden die anderen trotzdem geschrieben. Der Lauf wird anschließend als Fehler geloggt und im nächsten Intervall wiederholt.

`google` und `outlook` sind noch **nicht implementiert**. Ein unbekannter Modus wird mit einer Warnung ignoriert. Stattdessen nutzt die CLI `local` und der Scheduler `docker`.

## CalDAV

Mit `MODE=caldav` landet der Stundenplan direkt als normale Termine in einem Kalender auf deinem CalDAV-Server. Von dort synchronisieren ihn alle verbundenen Geräte. Ein Abo einer `.ics`-URL ist dafür nicht nötig.

```dotenv
MODE=caldav
CALDAV_URL=https://cloud.example.com/remote.php/dav
CALDAV_USERNAME=max
CALDAV_PASSWORD=app-passwort
CALDAV_CALENDAR=Stundenplan
```

### Server-Adressen

| Server    | `CALDAV_URL` | Hinweis |
|-----------|--------------|---------|
| Nextcloud | `https://<host>/remote.php/dav` | App-Passwort unter *Einstellungen → Sicherheit* anlegen |
| iCloud    | `https://caldav.icloud.com/` | Apple-ID als Benutzername, [app-spezifisches Passwort](https://support.apple.com/de-de/102654) verwenden |
| Radicale  | `http://<host>:5232/` | |
| Baïkal    | `https://<host>/dav.php` | |

Bei anderen Anbietern steht die CalDAV-Adresse in deren Hilfe. **Google Kalender** funktioniert nicht, weil Google für CalDAV OAuth verlangt.

### So funktioniert der Sync

- Jede Stunde bekommt eine feste UID aus der WebUntis-ID. Bei jedem Lauf werden die Termine auf dem Server mit dem aktuellen Stundenplan verglichen:
  - neue Stunden werden **angelegt**
  - Stunden mit geändertem Raum, Ausfall oder Vertretungstext werden **aktualisiert** (ausgefallene Stunden bleiben als abgesagter Termin stehen)
  - Stunden, die es in WebUntis nicht mehr gibt, werden **gelöscht**
  - Unveränderte Termine werden nicht angefasst.
- Abgeglichen wird nur der Zeitraum, den WebUntis gerade liefert (ab Montag der aktuellen Woche). **Ältere Stunden bleiben als Verlauf stehen.**
- Das Tool ändert **nur eigene Termine**. Diese erkennt es an einem Kürzel in der UID, das aus `SCHOOL` und `USERNAME` berechnet wird. Andere Termine im selben Kalender bleiben unberührt, ebenso Stundenpläne anderer WebUntis-Konten im selben Kalender. Ein eigener Kalender ist trotzdem übersichtlicher.
- Liefert WebUntis gar keine Stunden (Ferien oder ein Fehler beim Abruf), wird vorsichtshalber nichts gelöscht.
- Existiert `CALDAV_CALENDAR` noch nicht, wird er angelegt. Erlaubt der Server das nicht, den Kalender einmal von Hand mit genau diesem Namen anlegen.

### CalDAV mit Docker

Im Container funktioniert CalDAV ohne weitere Einrichtung: Die Zugangsdaten kommen wie alle anderen Werte aus der `.env`. Um zusätzlich die `.ics`-Datei im Volume zu behalten, beide Modi setzen:

```dotenv
MODE=docker,caldav
```

Läuft der CalDAV-Server auf demselben Rechner, zeigt `localhost` im Container auf den Container selbst. Dann stattdessen

- `http://host.docker.internal:<port>/…` verwenden (Docker Desktop; unter Linux zusätzlich `extra_hosts: ["host.docker.internal:host-gateway"]` in `docker-compose.yml`), oder
- den Servicenamen verwenden, wenn der Kalender-Server im selben Compose-Projekt läuft (z. B. `http://radicale:5232/`).

## Nutzung

### Mit Docker (empfohlen für Dauerbetrieb)

```bash
cp .env.example .env   # Zugangsdaten eintragen, MODE=docker (oder docker,caldav)
docker compose up -d --build
```

Der Container startet den Scheduler und schreibt den Stundenplan alle `UPDATE_INTERVAL` Minuten nach `./calendar-data/stundenplan.ics` auf dem Host bzw. in den CalDAV-Kalender.

Nach einem Update des Projekts das Image mit `--build` neu bauen, damit neue Abhängigkeiten installiert werden.

Logs ansehen:

```bash
docker compose logs -f untis-calendar
```

### Lokal mit Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

In der `.env` `MODE=local` setzen (die Vorlage steht auf `docker`, das nach `/data` schreibt).

Einmaliger Export (Ergebnis liegt in `CALENDAR_FILE`, standardmäßig `./stundenplan.ics`, bzw. im CalDAV-Kalender):

```bash
untis-calendar
```

Dauerbetrieb mit Intervall:

```bash
python -m untis_to_calendar.scheduler
```

> Die `.env` wird relativ zum Projektverzeichnis gesucht. Deshalb mit `pip install -e .` (editable) installieren oder die Variablen direkt als Umgebungsvariablen setzen.

## Kalender einbinden

Es gibt drei Wege:

- **CalDAV-Sync** (`MODE=caldav`, siehe [oben](#caldav)): Termine erscheinen direkt im Kalender, Änderungen kommen nach dem nächsten Lauf auf allen Geräten an.
- **Abonnieren** der `.ics`-Datei: Die Datei muss dafür über eine URL erreichbar sein, z. B. über einen Webserver, Nextcloud oder einen anderen Dateihoster, der das Verzeichnis `calendar-data/` ausliefert. Wie oft die Kalender-App neu lädt, bestimmt die App, oft nur alle paar Stunden.
- **Einmalig importieren** der `.ics`-Datei (in die Kalender-App ziehen). Änderungen am Stundenplan kommen dann aber nicht automatisch an.

Das Projekt selbst stellt keinen HTTP-Server bereit.

## Projektstruktur

```
src/untis_to_calendar/
├── cli.py              # Einmaliger Export (Entry-Point `untis-calendar`)
├── scheduler.py        # Endlosschleife mit Intervall (Docker-Entrypoint)
├── config.py           # Laden der Konfiguration aus .env / Umgebung
├── models.py           # UntisEvent: normalisiertes Kalender-Event
├── core/
│   ├── untis_client.py # Login, Schuljahr, Abruf des Stundenplans
│   └── transform.py    # WebUntis-Periode → UntisEvent (inkl. UID und Zeitzone)
└── sinks/
    ├── __init__.py     # SINKS-Registry: MODE → Sink
    ├── base.py         # Abstrakte Basisklasse CalendarSink
    ├── ical.py         # Gemeinsamer Aufbau von VEVENT/VCALENDAR
    ├── ics_local.py    # Modus `local`
    ├── ics_volume.py   # Modus `docker`
    └── caldav_sync.py  # Modus `caldav`
```

### Eigenes Backend hinzufügen

1. In `sinks/` eine Klasse anlegen, die von `CalendarSink` erbt, im Konstruktor die `Config` entgegennimmt und `write(self, events, window_start, window_end)` implementiert. `window_start` bis `window_end` (jeweils inklusive) ist der Zeitraum, den WebUntis geliefert hat. Ein synchronisierendes Backend darf Termine in diesem Zeitraum, die nicht mehr in `events` vorkommen, löschen.
2. Die Klasse im `SINKS`-Dictionary in `sinks/__init__.py` unter dem gewünschten `MODE`-Namen registrieren. CLI und Scheduler nutzen beide diese Registry.

Für den Kalenderinhalt `build_calendar()` aus `sinks/ical.py` verwenden, damit alle Ausgaben dieselben Termine erzeugen.

## Fehlerbehebung

- **`Login fehlgeschlagen`**: `SERVER`, `SCHOOL` und `USERNAME` exakt so eintragen wie in WebUntis, ohne Leerzeichen oder Anführungszeichen-Reste. Den Server-Namen und den Schulnamen findest du in der Browser-URL nach dem Login.
- **`Kein aktuelles Schuljahr gefunden`**: Heute liegt in keinem in WebUntis hinterlegten Schuljahr (z. B. in den Sommerferien).
- **`<VARIABLE> fehlt in .env`**: Eine Pflichtvariable ist leer oder die `.env` wird nicht gefunden (siehe Hinweis unter „Lokal mit Python“). Mit `MODE=caldav` ist auch `CALDAV_URL` Pflicht.
- **Leerer Kalender**: WebUntis liefert für den Zeitraum keine Stunden, z. B. in den Ferien.
- **CalDAV: `AuthorizationError … reason Unauthorized`** (HTTP 401): Benutzername oder Passwort falsch. Bei iCloud und Nextcloud mit Zwei-Faktor-Anmeldung ein App-Passwort verwenden. Bei `reason Forbidden` fehlt die Berechtigung für diese URL oder diesen Kalender.
- **CalDAV: Kalender kann nicht angelegt werden**: Den Kalender in der Weboberfläche des Servers mit genau dem Namen aus `CALDAV_CALENDAR` anlegen.
- **CalDAV im Container: `Connection refused`**: `CALDAV_URL` zeigt auf `localhost`. Siehe [CalDAV mit Docker](#caldav-mit-docker).
- **Termine doppelt im Kalender**: Wurde vorher eine mit einer älteren Version erzeugte `.ics`-Datei in denselben Kalender importiert, diese alten Termine einmal von Hand löschen. Sie haben keine UID des Tools, deshalb erkennt der Sync sie nicht als eigene Termine. Dasselbe gilt nach einer Änderung von `SCHOOL` oder `USERNAME`: Die bisherigen Termine gelten dann als fremd und bleiben stehen.
