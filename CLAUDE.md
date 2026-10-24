# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Fetches a personal WebUntis timetable (via the `webuntis` library) and writes it as an `.ics` file. User-facing strings, log messages, comments and docs (README, `.env.example`) are in **German**; identifiers and docstrings are in English. Keep that split.

## Commands

```bash
pip install -e ".[dev]"                  # editable install required (see .env note below)
untis-calendar                           # one-shot export (cli.main)
python -m untis_to_calendar.scheduler    # loop every UPDATE_INTERVAL minutes
docker compose up -d --build             # runs the scheduler, writes ./calendar-data/stundenplan.ics
```

There are no tests yet (pytest is in the `dev` extra but no test directory exists) and no linter/formatter is configured. Running anything for real needs valid WebUntis credentials in `.env`.

## Architecture

Pipeline: `Config.from_env` → `core.untis_client.get_timetable_events` → `(events, window_start, window_end)` → `sinks.write_to_sinks`, which calls `CalendarSink.write(events, window_start, window_end)` on every sink selected by `MODE`.

- **Config** (`config.py`): frozen dataclass. `MODE` may be a comma-separated list (`config.modes`). `uid_suffix` (hash of school+username) namespaces event UIDs per account. Has its own minimal `.env` parser (no python-dotenv) that **overwrites** `os.environ`. Both entry points locate `.env` as `Path(__file__).parent.parent.parent`, i.e. the repo root, which only works with an editable install or when running from source. Otherwise vars must come from the real environment (as in Docker via `env_file`).
- **Fetching** (`core/untis_client.py`): starts at Monday of the current week (next Monday on weekends, clamped to the school-year start), then probes `my_timetable` with growing end dates up to 19 days and keeps the last non-empty result. Raises if today is not inside a school year.
- **Transform** (`core/transform.py`): maps raw WebUntis periods to `UntisEvent`, attaching `TIMEZONE` to the naive WebUntis times and building a stable UID from `period.id` (hash fallback). UIDs must stay stable across substitutions: the CalDAV sink diffs by UID. Uses `getattr` fallbacks because the webuntis library's attribute names vary (`substText`/`subst_text`/…). Code `cancelled` becomes `cancelled=True` → `STATUS:CANCELLED`. `irregular` (substitution/moved lesson, usually takes place) stays a normal event unless `IRREGULAR_AS_CANCELLED=true`.
- **Sinks** (`sinks/`): `CalendarSink` ABC; constructor takes `Config` and must not do network I/O (the scheduler builds sinks once at startup). The single `SINKS` registry and `create_sinks`/`write_to_sinks` live in `sinks/__init__.py`. Unknown modes log a warning and fall back to `local` in the CLI, `docker` in the scheduler. `write_to_sinks` runs every sink even if one fails, then raises `SinkError` (logged without traceback by the scheduler). All sinks build iCalendar data through `sinks/ical.py` (UID, DTSTAMP, VTIMEZONE, `X-UNTIS-FINGERPRINT` content hash). `ics_local` writes `CALENDAR_FILE`; `ics_volume` always writes `DATA_DIR/stundenplan.ics` and ignores `CALENDAR_FILE`.
- **CalDAV** (`sinks/caldav_sync.py`): connects per `write()`. It finds or creates `CALDAV_CALENDAR` by display name, then reconciles inside `[window_start, window_end]`: create missing UIDs, update when the fingerprint differs, delete leftovers. It only touches UIDs ending in `config.uid_suffix`, never deletes when `events` is empty, and leaves events before the window as history. Needs caldav ≥ 3.5 (`UidConflictError`, `add_event`).
- `google` and `outlook` are not implemented.
- The scheduler's change detection (`get_events_hash`) only affects logging; sinks write every run.
- The Docker image's healthcheck only checks that the package imports.
