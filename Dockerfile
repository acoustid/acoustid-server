FROM ubuntu:18.04 as builder

RUN apt-get update && \
    apt-get install -y python python-pip python-virtualenv python-dev libchromaprint1 libchromaprint-tools git libpq-dev

ADD requirements.txt /tmp/requirements.txt

RUN virtualenv /opt/acoustid/server/venv && \
    /opt/acoustid/server/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY ./ /tmp/acoustid-server/
RUN (cd /tmp/acoustid-server/ && git archive --format=tar HEAD) | (cd /opt/acoustid/server/ && tar xf -)

FROM ubuntu:18.04

RUN apt-get update && \
    apt-get install -y python libchromaprint1 libchromaprint-tools uwsgi dumb-init

WORKDIR /opt/acoustid/server/
COPY --from=builder /opt/acoustid/server/ .

RUN useradd -ms /bin/bash acoustid
USER acoustid

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
