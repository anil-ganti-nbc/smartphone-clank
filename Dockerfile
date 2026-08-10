# Smartphone Clank -- Linux AMD64 staging image. Under construction / active
# development. Runs the one-shot collector runner (runtime/run_once.py),
# NOT the BlockingScheduler daemon (runtime/daemon.py) -- see
# docs/SCHEDULER_MIGRATION.md for the full behavioral mapping. An external
# scheduler (cron/systemd timer) invokes this repeatedly; each invocation
# checks every collector's due status against its own persisted run
# history and runs whichever are due, then exits.
FROM python:3.12-slim AS base

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin clank

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .
# Do not ship the dev-only .venv or test caches into the image (also
# covered by .dockerignore, kept here as defence in depth).
RUN rm -rf .venv .pytest_cache __pycache__

# Full Git SHA this image was built from. Must be passed at build time.
# Never derived from a .git directory at runtime -- none is copied into
# this image (excluded by .dockerignore). Pattern proven on OEM Radar /
# Chinese Tech Wire / Feature Phone Clank / Smartwatch Clank / Watch Clank.
ARG GIT_REVISION=unknown
LABEL clank.id="smartphone-clank" \
      org.opencontainers.image.revision="${GIT_REVISION}"
ENV CLANK_SOURCE_REVISION=${GIT_REVISION} \
    CLANK_LOCAL_CONFIG=config/config.docker.yaml \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Authoritative state (the SQLite DB) lives on a mounted volume, not the
# container filesystem.
RUN mkdir -p /app/data && chown -R clank:clank /app

USER clank

ENTRYPOINT ["python", "-m", "runtime.run_once"]
