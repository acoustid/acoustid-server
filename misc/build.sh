#!/usr/bin/env bash

set -ex

inkscape favicon.svg --export-png=favicon.png
convert favicon.png ../acoustid/web/static/favicon.ico
rm favicon.png

inkscape logo.svg --export-plain-svg=../acoustid/web/static/acoustid.svg
