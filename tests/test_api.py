# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.api import serialize_response


def test_serialize_json():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_response(data, 'json')
    assert 'application/json; charset=UTF-8' == resp.content_type
    expected = b'''{"artists": [{"cities": ["Paris", "Lyon"], "name": "Jean Michel Jarre", "year": 1948}], "status": "ok"}'''
    assert expected == resp.data


def test_serialize_jsonp():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_response(data, 'jsonp:getData')
    assert 'application/javascript; charset=UTF-8' == resp.content_type
    expected = b'''getData({"artists": [{"cities": ["Paris", "Lyon"], "name": "Jean Michel Jarre", "year": 1948}], "status": "ok"})'''
    assert expected == resp.data


def test_serialize_xml():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_response(data, 'xml')
    assert 'text/xml; charset=UTF-8' == resp.content_type
    expected = (
        b'''<?xml version='1.0' encoding='UTF-8'?>\n<response><artists><artist><cities><city>Paris</city><city>Lyon'''
        b'''</city></cities><name>Jean Michel Jarre</name><year>1948</year></artist></artists><status>ok</status></response>'''
    )
    assert expected == resp.data


def test_serialize_xml_attribute():
    data = {'@status': 'ok'}
    resp = serialize_response(data, 'xml')
    assert 'text/xml; charset=UTF-8' == resp.content_type
    expected = b'''<?xml version='1.0' encoding='UTF-8'?>\n<response status="ok" />'''
    assert expected == resp.data
