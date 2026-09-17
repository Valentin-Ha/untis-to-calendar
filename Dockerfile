FROM python:3.11-slim

WORKDIR /app

# Dependencies installieren
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir ".[dev]"

# Healthcheck für Container-Überwachung
HEALTHCHECK --interval=5m --timeout=30s --start-period=1m --retries=3 \
    CMD python -c "import untis_to_calendar" || exit 1

# Scheduler als Entrypoint
CMD ["python", "-m", "untis_to_calendar.scheduler"]