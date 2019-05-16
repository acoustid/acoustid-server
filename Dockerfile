FROM ubuntu:16.04

RUN apt-get update && \
    apt-get install -y \
        python python-pip python-virtualenv python-dev \
        libchromaprint0 libchromaprint-tools libpq-dev libffi-dev libssl-dev libpcre3-dev \
        curl

RUN curl -Lo /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.2/dumb-init_1.2.2_amd64 && \
    chmod +x /usr/local/bin/dumb-init

ADD requirements.txt /tmp/requirements.txt

RUN virtualenv /opt/acoustid/server.venv && \
    /opt/acoustid/server.venv/bin/pip install --no-binary :all: --no-cache-dir -r /tmp/requirements.txt

RUN useradd -ms /bin/bash acoustid
USER acoustid

WORKDIR /opt/acoustid/server/

COPY ./ /opt/acoustid/server/

ENTRYPOINT ["/usr/local/bin/dumb-init", "--"]
