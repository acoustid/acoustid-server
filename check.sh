#!/usr/bin/env bash

set -eux

tox -e flake8,mypy
tox -e py3
