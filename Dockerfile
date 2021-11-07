FROM ubuntu:20.04

RUN apt-get update && \
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        software-properties-common

RUN apt-get update && \
    apt-get install -y \
        gcc libchromaprint1 libchromaprint-tools libpq-dev libffi-dev libssl-dev libpcre3-dev \
        tini curl nginx

RUN add-apt-repository ppa:pypy/ppa && \
    apt-get update && \
    apt-get install -y \
        pypy3 \
        pypy3-dev \

RUN curl -Lo get-pip.py https://bootstrap.pypa.io/get-pip.py && \
    python get-pip.py && \
    pip install virtualenv

ADD requirements_py3.txt /tmp/requirements.txt

RUN virtualenv -p pypy3 /opt/acoustid/server.venv && \
    /opt/acoustid/server.venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /opt/acoustid/server/

COPY ./ /opt/acoustid/server/

RUN useradd -ms /bin/bash acoustid
USER acoustid

ENTRYPOINT ["/usr/bin/tini", "--"]
