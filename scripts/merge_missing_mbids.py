#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.script import run_script
from acoustid.scripts.merge_missing_mbids import main


run_script(main, master_only=True)
