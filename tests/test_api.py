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

TEST_2_LENGTH = 320
TEST_2_FP = 'AQABVtuUZFGShAqO-h9OHD96SvhwBVNCKQnOIYmiIc-ENwF7TDe8Hr0W_AjhvRCP2sfT4DTS7zjyOYeqaI-RSxee5RmaWzhOHnlcaB6HnPgpdE-DkWIH2ysYG_Eh9zJCyfCXGOdw-EGoD2p69IavWOhzMD-a9tBx9FgPVz2qNDvQH3744ISIXRKeHto5_MhyeMtxc-COnYJ_lHLwRAgPvShz_Hga4zd8HD9UKXWOPP3xRLmGnlbQHKfxGPeRvAt6UngMvcF-gkpRi0bUZjGaH6FUHb_xGDt6aHmM__ghfkmH70B4fWiuCj8y8uj3oImZY8d3NFWWHuGF-3hCPEd_uEOyE_nw4w8ueXi24znCHOHxSWtw9BnSBzrSHF2Y4S0e_EioZoh9XMGfo2dqNMeP80aQPM5xGT9efMeTYL-KIqmHdDraHs-P8IcYjoj0I7_Q43iJ9BF64nSKKth2SjG-cvCHH-2OL8txHsUt9HhF4LiK5j16lAf1FkjvQiN55FSOkkOPkmj4GK-OH80eIeyh98HhE_qhPwjzKAV-HJ2OZkd4Q_vhp0d_6Id-_IeWW9CKoP3RKM-Bo3mOfvhxND_6HMgZ6EfXHB-8Q8-iok1znOi-ozmx54P2Dg5V_PCgLxy8KiH6C0cbHU3Ebtiho9Rxw8er47tw7jgRNxl84ziPJ-B1_DiNNClzaGSCvMGPGxePMD5qZYEuAwdTXYSYcIkmodc2nMqg_WgqBk_yBdVx0vCjQD8uhNRxXTgvVFSOSOmx61C1KMaNsFwM93h-PBdmFm8o45nxDabx48cTbGl4hHuhasjSwPtxPvAV1A7yQMukREERR-nxL8j-EbWYQ8sj4joABQQmjQhkjLFCKSAo4QoxYiQwQhgmkGjCKGAIMMA4BIwQwjhAFMBUCCUAYEIxpYxUCDlEjJYOScSMgsIIAgADwjKEFBAUCkMEMYAagoARzAAHCDCIISKANkgYYBiQwgDDjHEMIGWZFUBQLhgohBGkhECOMEAMIYghogTgQghgiSLCYUegAsJApIQjxABNDFWCa6AIAQ4Q4KgAgIABgGDCMNGIMgQJRQAQTACpgBNIJkUcBMkpoKAgXCjAgAAGKIcYIVAYbZgwggkEmKLEiYGYAYQQShFAAAQBFEEAEuEIgwYRQoARnBkAmAGMEAGFGIgQBigCwAkABEIA'
TEST_2_FP_RAW = [-772063964, -772066012, -1007079116, -1011011276, -1027788492, -1029889740, -1031261916, -1031269084, -1031270620, -1031021744, -1031079600, -1031078425, -1031032346, -1018580506, -1018646290, -1022775046, -1056337446, -1056261686, -1073039030, -1073039013, -1068976005, -1001867175, -733365175, -733302711, -737435575, -603332504, -603365272, -737516311, -188076117, -175490390, -745993558, -758642022, -767030630, -1034347878, -1038412133, -1039584631, -1039654264, -1034345784, -1030086056, -1011141092, -1045873092, -1045939676, -1045947803, -2132276505, -2132259914, -2140415082, -2140472938, -2140481130, -2140546634, -2140603929, -2144802523, -2144536267, -2123540203, -2115147515, -2081855203, -2098598611, -2098606801, -2098606737, -2106995329, -2090217989, -2123638309, -2140477173, -2140477173, -2123634405, -2106992325, -2107061957, -2107061991, -2107007715, -1033140963, -1023769329, -1025864433, -1026913002, -1010133962, -1017409482, -1017540482, -1022848902, -1056337830, -1056271030, -1056261302, -1073038501, -1068975271, -1060587447, -993477559, -1001672631, -737435575, -737566615, -737550231, -737419031, 1422585259, 1955228586, 1367940010, 1388841914, 1380453258, 1376328586, 1376458634, 1107956618, 1107899017, 1113072281, 1121657497, 1119494811, 1135224479, 1135226615, 1139489511, 1130891874, 1126713938, 1109977859, 1114237187, 1122691331, 1122695431, 1122687255, 1114233125, 1130944869, 1126746469, 1097554247, 1105885511, 1105885511, 1135270230, 1122523494, 1114135910, 1109939695, 1093236223, 1076520335, 1080714635, 1089107851, 11092923, 11010986, 15209450, 15492074, 7103274, 2913082, 2905882, 2940681, 2947848, 7138056, 32303368, 61716744, 44932552, 1118668232, 1118406137, 1122600424, 1110167912, 1110167848, 1110106424, 1122689305, 1118495003, 1118478714, 1118540010, 1122599146, 1110016234, 1110147562, 1110094153, 1076535560, 1076538376, -1058363384, -794183656, -794249176, -790063064, -261519320, -261519319, -529562582, -529628886, -530153430, -530280406, -534465494, -534459350, -517027794, -517027778, -517056387, 1630428508, 1634606924, 1643060940, -508616995, -508740929, -475252054, -487834709, -496223301, -496231493, -496092485, -488752486, -489735542, -494125366, -494125542, 1641889598, 1627335998, 1617898782, 1613703454, 1614756622, 537664270, 541854222, 541854238, 541874782, 558651982, 558168910, 558168910, 558168398, 566360398, 1636039038, 1669593454, 1938028670, 1942087766, 1942087766, 1665394807, 1631779173, 1640192868, 1640221300, 1640483428, 1640487796, 1631902020, 1627682884, 553932868, 554654068, 554589029, 567179879, 562985575, 562846279, 562879301, 558684487, 554678646, 554678646, 558873462, 567262070, 563067366, 562936022, 567064775, 558692565, 1628436725, 1661925605, 1661893095, 1666087909, 592329573, 567032663, 567032133, 567032132, 1640840020, 1909340900, 1909340900, -238142748, -775079212, -775152956, -1043580220, -1047774524, -2121450764, -2138162460, -2138162460, -2138232091, -2121520409, -2117330313, -2124670345, -2124604585, -2092205227, -2083848891, -2083787451, -2117489195, -2117550619, -2124902943, -2139517453, -2139383405, -2122597997, -2122598221, -2093090639, -2095162991, -2107737727, -2107754111, -2108805231, -2099495199, -2099499291, -2097402137, -2098451465, -2098709513, -2098717737, -2081859113, -2123773481, -2140434985, -2140496425, -2140428906, -2132171338, -2132236874, -2065124170, -2023181130, -2039964482, -2044162882, -2044098306, -2111137761, -2111117043, -2111165684, -2144720372, -2140460532, -2132132340, -2136328643, -2136407507, -2136471761, -2136471761, -2132277457, -2114187977, -2091268651, -2083809851, -2083872379, -2117361257, -2117552729, -2141681241, -2139584009, -2143708937, -2143618857, -2126874411, -2126894891, -2093339196, -2105923644, -2099628348, -2103836012, -2103966047, -2099751259, -2097639449, -2031579161, -2039763466, -2031375914, -2014728234, -2056675370, -2056548654, -2073127278, -2077251950, -2077233262, -2077266510, -2077332302, -2073154382, -2014434126, -2031143722, -2039794617, -2039792379, -2039792868, -2107033028, -2081936836, -2136462820, -2136265204, -2136263155, -2136456385, -2136456401, -2132228626, -2122791506, -2091070041, -2107647561, -2108769915, -2100384379]


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
    # missing user
    values = MultiDict({'format': 'json', 'client': 'app1key'})
    params = SubmitHandlerParams()
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid user
    values = MultiDict({'format': 'json', 'client': 'app1key', 'user': 'N/A'})
    params = SubmitHandlerParams()
    assert_raises(errors.InvalidUserAPIKeyError, params.parse, values, conn)
    # missing fingerprint
    values = MultiDict({'format': 'json', 'client': 'app1key', 'user': 'user1key'})
    params = SubmitHandlerParams()
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # all ok (single submission)
    values = MultiDict({'format': 'json', 'client': 'app1key', 'user': 'user1key',
        'mbid': ['4d814cb1-20ec-494f-996f-f31ca8a49784', '66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea'],
        'puid': '4e823498-c77d-4bfb-b6cc-85b05c2783cf',
        'duration': str(TEST_1_LENGTH),
        'fingerprint': TEST_1_FP,
        'bitrate': '192',
        'fileformat': 'MP3'
    })
    params = SubmitHandlerParams()
    params.parse(values, conn)
    assert_equals(1, len(params.submissions))
    assert_equals(['4d814cb1-20ec-494f-996f-f31ca8a49784', '66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea'], params.submissions[0]['mbids'])
    assert_equals('4e823498-c77d-4bfb-b6cc-85b05c2783cf', params.submissions[0]['puid'])
    assert_equals(TEST_1_LENGTH, params.submissions[0]['duration'])
    assert_equals(TEST_1_FP_RAW, params.submissions[0]['fingerprint'])
    assert_equals(192, params.submissions[0]['bitrate'])
    assert_equals('MP3', params.submissions[0]['format'])
    # all ok (single submission)
    values = MultiDict({'format': 'json', 'client': 'app1key', 'user': 'user1key',
        'mbid.0': '4d814cb1-20ec-494f-996f-f31ca8a49784',
        'puid.0': '4e823498-c77d-4bfb-b6cc-85b05c2783cf',
        'duration.0': str(TEST_1_LENGTH),
        'fingerprint.0': TEST_1_FP,
        'bitrate.0': '192',
        'fileformat.0': 'MP3',
        'mbid.1': '66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea',
        'puid.1': '57b202a3-242b-4896-a79c-cac34bbca0b6',
        'duration.1': str(TEST_2_LENGTH),
        'fingerprint.1': TEST_2_FP,
        'bitrate.1': '500',
        'fileformat.1': 'FLAC',
    })
    params = SubmitHandlerParams()
    params.parse(values, conn)
    assert_equals(2, len(params.submissions))
    assert_equals(['4d814cb1-20ec-494f-996f-f31ca8a49784'], params.submissions[0]['mbids'])
    assert_equals('4e823498-c77d-4bfb-b6cc-85b05c2783cf', params.submissions[0]['puid'])
    assert_equals(TEST_1_LENGTH, params.submissions[0]['duration'])
    assert_equals(TEST_1_FP_RAW, params.submissions[0]['fingerprint'])
    assert_equals(192, params.submissions[0]['bitrate'])
    assert_equals('MP3', params.submissions[0]['format'])
    assert_equals(['66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea'], params.submissions[1]['mbids'])
    assert_equals('57b202a3-242b-4896-a79c-cac34bbca0b6', params.submissions[1]['puid'])
    assert_equals(TEST_2_LENGTH, params.submissions[1]['duration'])
    assert_equals(TEST_2_FP_RAW, params.submissions[1]['fingerprint'])
    assert_equals(500, params.submissions[1]['bitrate'])
    assert_equals('FLAC', params.submissions[1]['format'])

