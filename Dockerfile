FROM ubuntu:24.04 AS chromaprint-build

RUN apt-get update && \
    apt-get install -y --no-install-recommends cmake make gcc g++ curl ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/chromaprint

ARG CHROMAPRINT_VERSION=1.6.1
# Release assets can be replaced after the fact, so the tarball is pinned by
# digest rather than by name. Both have to be changed together.
ARG CHROMAPRINT_SHA256=3368805af0ee47b9df74df10b5001a44569e01df2844dab520031720dde9ad23

RUN curl --fail --show-error --silent --location https://github.com/acoustid/chromaprint/releases/download/v${CHROMAPRINT_VERSION}/chromaprint-${CHROMAPRINT_VERSION}.tar.gz -o chromaprint.tar.gz && \
    echo "${CHROMAPRINT_SHA256}  chromaprint.tar.gz" | sha256sum --check --strict - && \
    tar xzf chromaprint.tar.gz && \
    cd chromaprint-${CHROMAPRINT_VERSION} && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_C_FLAGS="-O3 -march=haswell -ffast-math" -DCMAKE_CXX_FLAGS="-O3 -march=haswell -ffast-math" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF && \
    make -j$(nproc) && \
    make install DESTDIR=/opt/chromaprint/install

FROM ubuntu:24.04 AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-venv \
        libpq5 libffi8 libssl3 libpcre3 \
        curl nginx dumb-init && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=chromaprint-build /opt/chromaprint/install/usr/ /usr/

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /uvx /bin/

RUN useradd -ms /bin/bash acoustid
WORKDIR /opt/acoustid/server

FROM base AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-dev python3-venv gcc \
        libpq-dev libffi-dev libssl-dev libpcre3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-install-package acoustid-ext

COPY libs /opt/acoustid/server/libs

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    CFLAGS="-O3 -march=haswell -ffast-math" \
    uv sync --frozen --no-install-project

FROM base

COPY --from=builder /opt/acoustid/server/.venv /opt/acoustid/server/.venv

COPY . /opt/acoustid/server

USER acoustid

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
