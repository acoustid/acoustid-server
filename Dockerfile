FROM ubuntu:16.04 AS builder

RUN apt-get update && \
    apt-get install -y \
        python python-dev gcc \
        libchromaprint0 libchromaprint-tools libpq-dev libffi-dev libssl-dev libpcre3-dev \
        curl

RUN curl -Lo get-pip.py https://bootstrap.pypa.io/get-pip.py && \
    python get-pip.py && \
    pip install virtualenv

ADD requirements_py2.txt /tmp/requirements.txt

RUN virtualenv /opt/acoustid/server.venv && \
    /opt/acoustid/server.venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY ./ /opt/acoustid/server/

FROM ubuntu:16.04

RUN apt-get update && \
    apt-get install -y \
        python \
        libchromaprint0 libchromaprint-tools libpq5 libffi6 libssl1.0.0 libpcre3 \
        curl

RUN curl -Lo /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.2/dumb-init_1.2.2_amd64 && \
    chmod +x /usr/local/bin/dumb-init

RUN useradd -ms /bin/bash acoustid
USER acoustid

COPY --from=builder /opt/acoustid/server/ /opt/acoustid/server/

WORKDIR /opt/acoustid/server/

ENTRYPOINT ["/usr/local/bin/dumb-init", "--"]
