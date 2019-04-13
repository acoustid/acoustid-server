FROM ubuntu:18.04

RUN useradd -ms /bin/bash acoustid
USER acoustid

WORKDIR /opt/acoustid/server/

RUN apt-get update && \
    apt-get install -y \
        python python-pip python-virtualenv python-dev \
        libchromaprint1 libchromaprint-tools libpq-dev \
        dumb-init curl

ADD requirements.txt /tmp/requirements.txt

RUN virtualenv /opt/acoustid/server.venv && \
    /opt/acoustid/server.venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY ./ /opt/acoustid/server/

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
