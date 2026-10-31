FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/meridian

# Copy project files from build context
COPY services/api/pyproject.toml ./services/api/
COPY services/api/app ./services/api/app
RUN pip install --no-cache-dir ./services/api

COPY alembic.ini ./
COPY migrations ./migrations

# Non-root execution for the API process.
RUN useradd --create-home --uid 10001 meridian
RUN chown -R meridian:meridian /srv/meridian
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "services/api", "--host", "0.0.0.0", "--port", "8000"]
