FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y \
        python3 python3-dev python3-venv gcc \
        libchromaprint1 libchromaprint-tools libpq-dev libffi-dev libssl-dev libpcre3-dev \
        curl nginx dumb-init

ADD requirements.txt /tmp/requirements.txt

RUN python3 -m venv /opt/acoustid/server.venv && \
    /opt/acoustid/server.venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /opt/acoustid/server/

COPY ./ /opt/acoustid/server/

RUN useradd -ms /bin/bash acoustid
USER acoustid

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
