FROM ubuntu:20.04

RUN apt-get update && \
    apt-get install -y \
        python3 python3-dev gcc \
        libchromaprint1 libchromaprint-tools libpq-dev libffi-dev libssl-dev libpcre3-dev tini \
        curl

RUN curl -Lo get-pip.py https://bootstrap.pypa.io/get-pip.py. && \
    python get-pip.py && \
    pip install virtualenv

ADD requirements_py3.txt /tmp/requirements.txt

RUN virtualenv /opt/acoustid/server.venv && \
    /opt/acoustid/server.venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /opt/acoustid/server/

COPY ./ /opt/acoustid/server/

RUN useradd -ms /bin/bash acoustid
USER acoustid

ENTRYPOINT ["/usr/bin/tini", "--"]
