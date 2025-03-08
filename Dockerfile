
FROM ubuntu:24.04 AS base

RUN apt-get update && \
    apt-get install -y \
        python3 python3-venv \
        libchromaprint1 libchromaprint-tools libpq5 libffi8 libssl3 libpcre3 \
        curl nginx dumb-init

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN useradd -ms /bin/bash acoustid
WORKDIR /opt/acoustid/server

FROM base AS builder

RUN apt-get update && \
    apt-get install -y \
        python3 python3-dev python3-venv gcc \
        libchromaprint1 libchromaprint-tools libpq-dev libffi-dev libssl-dev libpcre3-dev

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

FROM base

COPY --from=builder /opt/acoustid/server/.venv /opt/acoustid/server/.venv

COPY . /opt/acoustid/server

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

USER acoustid

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
