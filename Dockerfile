FROM python:3.11-slim

WORKDIR /app

# Dependencies installieren
COPY pyproject.toml LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir "."

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin untis \
    && mkdir -p /data \
    && chown untis:untis /data
USER untis

# Healthcheck für Container-Überwachung
HEALTHCHECK --interval=5m --timeout=30s --start-period=1m --retries=3 \
    CMD python -c "import untis_to_calendar" || exit 1

# Scheduler als Entrypoint
CMD ["python", "-m", "untis_to_calendar.scheduler"]