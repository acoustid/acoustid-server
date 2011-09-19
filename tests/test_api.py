# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import *
from tests import prepare_database, with_database, assert_json_equals
from acoustid.api import serialize_response


def test_serialize_json():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_response(data, 'json')
    assert_equals('application/json; charset=UTF-8', resp.content_type)
    expected = '''{"status": "ok", "artists": [{"cities": ["Paris", "Lyon"], "name": "Jean Michel Jarre", "year": 1948}]}'''
    assert_equals(expected, resp.data)


def test_serialize_jsonp():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_response(data, 'jsonp:getData')
    assert_equals('application/javascript; charset=UTF-8', resp.content_type)
    expected = '''getData({"status": "ok", "artists": [{"cities": ["Paris", "Lyon"], "name": "Jean Michel Jarre", "year": 1948}]})'''
    assert_equals(expected, resp.data)


def test_serialize_xml():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_response(data, 'xml')
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = '''<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><artists><artist><cities><city>Paris</city><city>Lyon</city></cities><name>Jean Michel Jarre</name><year>1948</year></artist></artists></response>'''
    assert_equals(expected, resp.data)


def test_serialize_xml_attribute():
    data = {'@status': 'ok'}
    resp = serialize_response(data, 'xml')
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = '''<?xml version='1.0' encoding='UTF-8'?>\n<response status="ok" />'''
    assert_equals(expected, resp.data)

