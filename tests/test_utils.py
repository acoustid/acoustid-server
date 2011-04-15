# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

from nose.tools import *
from acoustid.utils import singular


def test_singular():
    assert_equals('artist', singular('artists'))
    assert_equals('release', singular('releases'))
    assert_equals('city', singular('cities'))

