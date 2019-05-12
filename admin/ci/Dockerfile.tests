FROM ubuntu:18.04

RUN apt-get update && \
    apt-get install -y \
        python python-pip python-virtualenv python-dev \
        libchromaprint1 libchromaprint-tools libpq-dev \
        python-tox curl

RUN curl -L -o /wait-for-it.sh https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh
RUN chmod +rx /wait-for-it.sh
