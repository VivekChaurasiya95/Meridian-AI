FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/meridian

# The worker calls the API service layer directly (D45: no worker HTTP
# credentials), so it installs the same runtime dependencies.
COPY services/api/pyproject.toml ./services/api/
COPY services/api/app ./services/api/app
RUN pip install --no-cache-dir ./services/api

COPY services/worker/main.py ./services/worker/main.py
COPY services/worker/sandbox ./services/worker/sandbox
COPY services/worker/security ./services/worker/security

# Isolated unprivileged execution user (ADR-006: non-root execution).
# M5+ untrusted execution must run as an even more restricted identity.
RUN useradd --create-home --uid 10002 meridian-sandbox
RUN chown -R meridian-sandbox:meridian-sandbox /srv/meridian
USER 10002

ENTRYPOINT ["python", "services/worker/main.py"]
