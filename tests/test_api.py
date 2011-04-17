# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

from nose.tools import *
from tests import prepare_database, with_database, assert_json_equals
from werkzeug.wrappers import Request
from werkzeug.test import EnvironBuilder
from werkzeug.datastructures import MultiDict
from acoustid.api import (
    serialize_json, serialize_xml, ok, error,
    LookupHandler,
    LookupHandlerParams,
    SubmitHandlerParams,
)
from acoustid import api as errors


TEST_1_LENGTH = 223
TEST_1_FP = 'AQABVokWyYm0JEGPS1EQWjnG0kGu7fhzVD6aZ9DxBh17QT-0Qx7Xw01i4yV2QYvQQ8fpo2GFhzH6KMef40cnKXj8wneg83B36Gh0Cy-j4ywsD-WL5lC94zmayUerQ5eIJteNcFPRIJKT_LiY5fh-NA-0Ez-6Hc9qojr-o6JooQmTbMIfyyh9FVMeQ88Ro5RzolVMPFIe_HB15KnxJcnRRryQqtrxDo7xYztnog9CHopCLkZQ-mie6viidDi-DnkO1XQQRkcvT3giHc9Y9EeT5_hl7BFRUTouXmBWPMsxqdnRFE-KHn4itKuI6seUiviS5MPRZF3APDsiSsmF69CCL0hLBSGnGauXBrqQOnxwOfhLFW0vhPmgR4mRS8d01OlxCZUzNLpwTWmQLz10hA2PJs5x5vjRhJKOXUTz5biS5cUlHcweOM6K7IceIuUITJIS9uiaJ2hCafiOS0X49nAPlTf8pcNDCWl6om9QW0eYH3oYDUGL5smxq8xxHj2ia8edQ9Qnoj_yksJ7TD3RfCdx60GOiuJBWT6s6TL6YhIVZUfTHHlyHA3HDk9mjIcrDd2SrAR9NLkShLyxR4LKo0GOS8kqhPEhe0YuBVN8lDr2EqHOpNCCfDSeBaUe_EP_oXJg3ciD5NM3mJEk_MetYXsu_GrgUD164dqP7MoyEo1zoxuP8FmFuyH8HMyP23jSSpjS7Sg-Tke-_XjCQT3C-vAz4ZJQtccfHHaY46OE90SYoMe_QqPYwRRO-DneMBDPo8vxaHmGR0eDST_q5vCFWzu2G91U_NvQ5EdPbejR_LgO9UK_oyFxHTiqV4DI8VB5WD_wjUF6Bj2eCGHUSbgzQzzqHX_R5Dm0SUS-BH2Jrcd5NM-OfEcPLedwOsdZ9LrgzsUjwmkY1MrR6Wkw-kCv49CLxjnaBR-OaxI0PSccDv_RNbRQG-LHwe-FHrkSBV1JIv0CR8xRqFcOjTrRiMWjAsWkEAYIDCQChFjCMBEAKAGAMU4ZoRBSngiBCCJMCQmAQAAIAAQQFjAkjQAGAKMMEMQapghAgDAElABGIFKUpUYBoxAwDDmiFBOSCYCAAFQQQxADhQAAGFKCCwKQEJAoBihwBAADEJGEIGIQcsAIIYQBCAgEiCCKKOMAAYApRIQAgDhikFBMAcYYFEIgQZRyACnCmEKCEAUEEQ4AQhQDSAAAjABACGMRAQIQgYQBBDBCnCAKOUEEAUBQA6gACFgAhBNICIwEEkIYRixgjBAHLAMiMWaAEIwoQIiiAAAliAHCCiSKgEAZYYATACgDFDDGAA'
TEST_1_FP_RAW = [2091780811, 2091846363, 2092194523, 1555328714, 1557456526, 1574290319, 1607909775, -539569697, -539500049, -539631123, -539728403, -581603971, -581080705, -585275027, 1566518767, 1599541711, 1601503695, 1607795147, 1607795065, 1607803241, 1607803755, 1599350571, 1599431963, 1607892251, 1599589643, 1465175371, 1431629131, 1431603163, 1951760859, 1977057787, 2111214073, 2144777689, 2136389083, 2115482987, 1981588971, 1981080043, 1981137227, 1985462363, 1985396843, 2002145321, 1968594985, 1951884569, 2086104841, 2086042123, 1557584507, 1557450474, 1557450458, -573246769, -539507825, -556351025, -556338689, -556277267, -539631123, -548018819, -44193411, -48387795, -65033427, -44122243, -42499315, 2146730253, 1867825181, 1863663657, 1846878251, 1846878314, 2132157818, 2136096618, 2140277482, 2005928682, 1972379338, 1955868363, 1960105931, 1557512667, 1574408570, 1574350970, 1574346778, 1565962266, 2136973374, 2136776750, 2136842559, 2145288969, 2145288968, 2147402264, -10534360, -48486872, -65264088, -65720536, 2081759017, 2094272363, 2111049690, 2006273994, 1989670858, 1993724362, 2127876570, 2144645546, -44785238, -35675730, -44042754, 1566432766, 1566428518, 1600060774, -547461838, -547462910, -548007678, -548011758, -547917518, -539139294, -555785358, -555845818, -536998970, -536933434, -537310794, -570918482, -591895317, -593993237, -593993255, -593890855, -593840648, -589587223, -602358675, -652690321, -551967666, -551902898, -27361010, -16858338, -19217617, -27692243, -11001044, -44555464, -61264088, -61261272, -61339016, -61257016, -35660088, -2242615, -2308149, -10714662, -44256854, -60841558, -52518486, -1126173222, -1126310434, -1134801426, -1654687762, -1621220370, -1629609098, -1627450602, -1629551841, -1629670627, -1629740740, -1629740740, -553829272, -579007240, -578856824, -595624824, -599925624, 1545393305, 1545130169, 1562170619, 1600124123, 1600038235, 1568582970, 1568515370, 2105057594, 2104013067, 2113831177, 2113831176, 2113831704, 2105471784, -48437460, -65245396, -65179844, 2082422585, 2086604665, 2094354395, 2111129547, 2012698570, 1995953098, 1993724382, -27987474, -2842194, -2825809, -36309505, -572662313, 1599981943, 1600117095, -547984077, -564764413, -562687742, -562691838, -547941582, -539663566, -539139210, -539019434, -570553402, -587331122, -587642434, -591902545, -591862613, -593960727, -593960743, -593960488, -572877608, -581264151, -585384853, -585569174, -552016802, -551886514, -547438262, -23412453, -23412439, -19147992, -19340504, -10951112, -48697800, -63373784, -63385992, -59126056, -59113767, -178661414, -178486790, -1252163334, -1252011846, -1272979298, -1404051042, -330435074, -330441234, -1395832338, -1109492249, -1076468265, -1093263033, -1099493034, -1104084714, -1106169546, -1101979346, -1630330578, -1684980434, -1718609638, -1718609654, -1651164342, -573235253, -572783669, -572767351, -539180648, -539364936, -539384648, -547836696, -549929752, -549929496, 1597744584, 1597956424, 2101264456, 2101264441, 2101231657, 1545494569, 1549149499, 1549152027, 1549155867, 1557552699, 1557481083, 1574196825, 1607751625, 1448460745, 1583268297, 1583268345, 1600053677, 1608476093, 1566533021, 1549612509, 1549080057, 1549205865, 360128873, 393552153, 374354185, 382742809, 399585577, 398533929, 398484843, 364967291, 364959563, 356550475, 356550475, 356681547, 358000411, 358000411, 894940473, 903328123, 936817115, 936817115, 912232923, 912032250, 907837930, 907932138, 907501915, 911626523, 374755641, 391542057, 1431725353, 1414882649, 1414918091, 1414911690, 1417135834, 1425523454, 1442305022, 1475797966, 1459024335, 1456927199, 1457512941, 1474094509, 1473015213, 1431059901, 1413749149, 1413812125, 1413879805, 1414931437, 1439703421, 365965625, 365965625, 399532329, 391143721, 391177515, 390135067, 390123275, 390237963, 390238027, 391620427, 894740249, 894731129, 1968537977, 2010624489, 2010559993, 2001180123, 1917158907, 1917093355, 1917317610, 1935073658, 1935110491, 1901543483, 1901543467, 1968627817, 1950803323, 1950870987, 1950743499]


def test_serialize_json():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_json(data)
    assert_equals('text/json', resp.content_type)
    expected = '''{"status": "ok", "artists": [{"cities": ["Paris", "Lyon"], "name": "Jean Michel Jarre", "year": 1948}]}'''
    assert_equals(expected, resp.data)


def test_serialize_xml():
    data = {'status': 'ok', 'artists': [{'name': 'Jean Michel Jarre', 'year': 1948, 'cities': ['Paris', 'Lyon']}]}
    resp = serialize_xml(data)
    assert_equals('text/xml', resp.content_type)
    expected = '''<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><artists><artist><cities><city>Paris</city><city>Lyon</city></cities><name>Jean Michel Jarre</name><year>1948</year></artist></artists></response>'''
    assert_equals(expected, resp.data)


def test_ok():
    resp = ok({'tracks': [{'id': 1, 'name': 'Track 1'}]}, 'json')
    assert_equals('text/json', resp.content_type)
    expected = '{"status": "ok", "tracks": [{"id": 1, "name": "Track 1"}]}'
    assert_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)


def test_error():
    resp = error(123, 'something is wrong', 'json')
    assert_equals('text/json', resp.content_type)
    expected = '{"status": "error", "error": {"message": "something is wrong", "code": 123}}'
    assert_equals(expected, resp.data)
    assert_equals('400 BAD REQUEST', resp.status)
    resp = error(234, 'oops', 'json', status=500)
    assert_equals('text/json', resp.content_type)
    expected = '{"status": "error", "error": {"message": "oops", "code": 234}}'
    assert_equals(expected, resp.data)
    assert_equals('500 INTERNAL SERVER ERROR', resp.status)


@with_database
def test_lookup_handler_params(conn):
    # invalid format
    values = MultiDict({'format': 'xls'})
    params = LookupHandlerParams()
    assert_raises(errors.UnknownFormatError, params.parse, values, conn)
    # missing client
    values = MultiDict({'format': 'json'})
    params = LookupHandlerParams()
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid client
    values = MultiDict({'format': 'json', 'client': 'N/A'})
    params = LookupHandlerParams()
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, conn)
    # missing duration
    values = MultiDict({'format': 'json', 'client': 'app1key'})
    params = LookupHandlerParams()
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # missing fingerprint
    values = MultiDict({'format': 'json', 'client': 'app1key', 'duration': str(TEST_1_LENGTH)})
    params = LookupHandlerParams()
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid fingerprint
    values = MultiDict({'format': 'json', 'client': 'app1key', 'duration': str(TEST_1_LENGTH), 'fingerprint': '...'})
    params = LookupHandlerParams()
    assert_raises(errors.InvalidFingerprintError, params.parse, values, conn)
    # all ok
    values = MultiDict({'format': 'json', 'client': 'app1key', 'duration': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP})
    params = LookupHandlerParams()
    params.parse(values, conn)
    assert_equals('json', params.format)
    assert_equals(1, params.application_id)
    assert_equals(TEST_1_LENGTH, params.duration)
    assert_equals(TEST_1_FP_RAW, params.fingerprint)


@with_database
def test_lookup_handler(conn):
    values = {'format': 'json', 'client': 'app1key', 'duration': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP}
    builder = EnvironBuilder(method='POST', data=values)
    handler = LookupHandler(conn=conn)
    # no matches
    handler = LookupHandler(conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/json', resp.content_type)
    expected = {
        "status": "ok",
        "results": []
    }
    assert_json_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)
    # one exact match
    prepare_database(conn, """
INSERT INTO fingerprint (length, fingerprint, source_id, track_id)
    VALUES (%s, %s, 1, 1);
""", (TEST_1_LENGTH, TEST_1_FP_RAW))
    handler = LookupHandler(conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/json', resp.content_type)
    expected = {
        "status": "ok",
        "results": [{
            "id": 1,
            "score": 1.0,
        }],
    }
    assert_json_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)
    # one exact match with MBIDs
    values = {'format': 'json', 'client': 'app1key', 'duration': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP, 'meta': '1'}
    builder = EnvironBuilder(method='POST', data=values)
    handler = LookupHandler(conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/json', resp.content_type)
    expected = {
        "status": "ok",
        "results": [{
            "id": 1,
            "score": 1.0,
            "recordings": [{"id": "b81f83ee-4da4-11e0-9ed8-0025225356f3"}],
        }],
    }
    assert_json_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)
    # one exact match with MBIDs and metadata
    values = {'format': 'json', 'client': 'app1key', 'duration': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP, 'meta': '2'}
    builder = EnvironBuilder(method='POST', data=values)
    handler = LookupHandler(conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/json', resp.content_type)
    expected = {
        "status": "ok",
        "results": [{
            "id": 1,
            "score": 1.0,
            "recordings": [{
                "id": "b81f83ee-4da4-11e0-9ed8-0025225356f3",
                "name": "Track A",
                "length": 123,
                "releases": [{
                    "id": "dd6c2cca-a0e9-4cc4-9a5f-7170bd098e23",
                    "name": "Album A",
                    "track_num": 1,
                    "track_count": 2,
                }],
                "artist": {
                    "id": "a64796c0-4da4-11e0-bf81-0025225356f3",
                    "name": "Artist A",
                },
            }],
        }]
    }
    assert_json_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)


@with_database
def test_submit_handler_params(conn):
    # invalid format
    values = MultiDict({'format': 'xls'})
    params = SubmitHandlerParams()
    assert_raises(errors.UnknownFormatError, params.parse, values, conn)
    # missing client
    values = MultiDict({'format': 'json'})
    params = SubmitHandlerParams()
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid client
    values = MultiDict({'format': 'json', 'client': 'N/A'})
    params = SubmitHandlerParams()
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, conn)
    # missing duration
    values = MultiDict({'format': 'json', 'client': 'app1key'})
    params = SubmitHandlerParams()
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
