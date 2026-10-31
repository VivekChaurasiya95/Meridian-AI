FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/meridian-worker

# Install base tools for inspection and git reproduction
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Isolated unprivileged execution user (ADR-006: non-root execution)
RUN useradd --create-home --uid 10002 meridian-sandbox

WORKDIR /workspace
RUN chown -R meridian-sandbox:meridian-sandbox /workspace

COPY main.py /srv/meridian-worker/main.py

USER 10002

ENTRYPOINT ["python", "/srv/meridian-worker/main.py"]
