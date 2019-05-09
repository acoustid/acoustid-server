# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals
from uuid import UUID
from tests import (
    prepare_database, with_database,
    TEST_1A_FP_RAW,
    TEST_1A_LENGTH,
    TEST_1B_FP_RAW,
    TEST_1B_LENGTH,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
)
from acoustid.data.track import (
    merge_missing_mbids, insert_track, merge_tracks,
    merge_mbids,
    can_merge_tracks,
    can_add_fp_to_track,
)
from acoustid.data.submission import insert_submission


@with_database
def test_merge_mbids(conn):
    insert_submission(conn, {'fingerprint': [1], 'length': 123, 'source_id': 1})
    insert_submission(conn, {'fingerprint': [1], 'length': 123, 'source_id': 1})
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (1, 1, '97edb73c-4dac-11e0-9096-0025225356f3', 9);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (2, 1, 'd575d506-4da4-11e0-b951-0025225356f3', 11);
INSERT INTO track_mbid_source (track_mbid_id, submission_id, source_id) VALUES (1, 1, 1);
INSERT INTO track_mbid_source (track_mbid_id, submission_id, source_id) VALUES (2, 2, 1);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (1, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (2, 1, true);
""")
    merge_mbids(conn, '97edb73c-4dac-11e0-9096-0025225356f3', ['d575d506-4da4-11e0-b951-0025225356f3'])
    rows = conn.execute("SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 20, False),
    ]
    assert_equals(expected_rows, rows)
    rows = conn.execute("SELECT track_mbid_id, submission_id, source_id FROM track_mbid_source ORDER BY track_mbid_id, submission_id, source_id").fetchall()
    expected_rows = [
        (1, 1, 1),
        (1, 2, 1),
    ]
    assert_equals(expected_rows, rows)
    rows = conn.execute("SELECT track_mbid_id, account_id FROM track_mbid_change ORDER BY track_mbid_id, account_id").fetchall()
    expected_rows = [
        (1, 1),
        (1, 1),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_merge_mbids_disabled_target(conn):
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 11);
""")
    merge_mbids(conn, '97edb73c-4dac-11e0-9096-0025225356f3', ['d575d506-4da4-11e0-b951-0025225356f3'])
    rows = conn.execute("SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 20, False),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_merge_mbids_disabled_source(conn):
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 11, true);
""")
    merge_mbids(conn, '97edb73c-4dac-11e0-9096-0025225356f3', ['d575d506-4da4-11e0-b951-0025225356f3'])
    rows = conn.execute("SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 20, False),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_merge_mbids_disabled_both(conn):
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 11, true);
""")
    merge_mbids(conn, '97edb73c-4dac-11e0-9096-0025225356f3', ['d575d506-4da4-11e0-b951-0025225356f3'])
    rows = conn.execute("SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 20, True),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_merge_missing_mbids(conn):
    from sqlalchemy.orm import Session
    from mbdata.sample_data import create_sample_data
    create_sample_data(Session(conn))
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, 'b81f83ee-4da4-11e0-9ed8-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (2, 'd575d506-4da4-11e0-b951-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (3, '97edb73c-4dac-11e0-9096-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (4, '5d0290a6-4dad-11e0-a47a-0025225356f3', 1);
INSERT INTO musicbrainz.recording_gid_redirect (new_id, gid) VALUES
    (7134047, 'd575d506-4da4-11e0-b951-0025225356f3'),
    (7134048, '5d0290a6-4dad-11e0-a47a-0025225356f3'),
    (7134049, 'b44dfb2a-4dad-11e0-bae4-0025225356f3');
""")
    merge_missing_mbids(conn)
    rows = conn.execute("SELECT track_id, mbid FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('77ef7468-e8f8-4447-9c7e-52b11272c6cc')),
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3')),
        (1, UUID('b81f83ee-4da4-11e0-9ed8-0025225356f3')),
        (2, UUID('77ef7468-e8f8-4447-9c7e-52b11272c6cc')),
        (3, UUID('97edb73c-4dac-11e0-9096-0025225356f3')),
        (4, UUID('e6d2be9c-06b7-4a64-911d-076ad4e79c6f')),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_insert_track(conn):
    id = insert_track(conn)
    assert_equals(5, id)
    id = insert_track(conn)
    assert_equals(6, id)


@with_database
def test_merge_tracks(conn):
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (%(fp1)s, %(len1)s, 1, 1), (%(fp2)s, %(len2)s, 2, 1);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (1, 1, '97edb73c-4dac-11e0-9096-0025225356f3', 10);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (2, 1, 'd575d506-4da4-11e0-b951-0025225356f3', 15);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (3, 2, 'd575d506-4da4-11e0-b951-0025225356f3', 50);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (4, 3, '97edb73c-4dac-11e0-9096-0025225356f3', 25);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (5, 4, '5d0290a6-4dad-11e0-a47a-0025225356f3', 30);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f4', 10);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f4', 15);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (2, 'd575d506-4da4-11e0-b951-0025225356f4', 50);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (3, '97edb73c-4dac-11e0-9096-0025225356f4', 25);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (4, '5d0290a6-4dad-11e0-a47a-0025225356f4', 30);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (2, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (3, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (4, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (5, 1, true);
    """, dict(fp1=TEST_1A_FP_RAW, len1=TEST_1A_LENGTH,
              fp2=TEST_1B_FP_RAW, len2=TEST_1B_LENGTH))
    merge_tracks(conn, 3, [1, 2, 4])
    rows = conn.execute("SELECT id, track_id FROM fingerprint ORDER BY id").fetchall()
    assert_equals([(1, 3), (2, 3)], rows)
    rows = conn.execute("SELECT id, track_id, mbid, submission_count FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected = [
        (5, 3, UUID('5d0290a6-4dad-11e0-a47a-0025225356f3'), 30),
        (1, 3, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 35),
        (2, 3, UUID('d575d506-4da4-11e0-b951-0025225356f3'), 65)
    ]
    assert_equals(expected, rows)
    rows = conn.execute("SELECT track_id, puid, submission_count FROM track_puid ORDER BY track_id, puid").fetchall()
    expected = [
        (3, UUID('5d0290a6-4dad-11e0-a47a-0025225356f4'), 30),
        (3, UUID('97edb73c-4dac-11e0-9096-0025225356f4'), 35),
        (3, UUID('d575d506-4da4-11e0-b951-0025225356f4'), 65)
    ]
    assert_equals(expected, rows)
    rows = conn.execute("SELECT track_mbid_id, account_id FROM track_mbid_change ORDER BY track_mbid_id, account_id").fetchall()
    expected_rows = [(1, 1), (2, 1), (2, 1), (5, 1)]
    assert_equals(expected_rows, rows)
    rows = conn.execute("SELECT id, new_id FROM track ORDER BY id, new_id").fetchall()
    assert_equals([(1, 3), (2, 3), (3, None), (4, 3)], rows)


@with_database
def test_merge_tracks_disabled_target(conn):
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (2, '97edb73c-4dac-11e0-9096-0025225356f3', 11);
""")
    merge_tracks(conn, 1, [2])
    rows = conn.execute("SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 20, False),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_merge_tracks_disabled_source(conn):
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (2, '97edb73c-4dac-11e0-9096-0025225356f3', 11, true);
""")
    merge_tracks(conn, 1, [2])
    rows = conn.execute("SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 20, False),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_merge_tracks_disabled_both(conn):
    prepare_database(conn, """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (2, '97edb73c-4dac-11e0-9096-0025225356f3', 11, true);
""")
    merge_tracks(conn, 1, [2])
    rows = conn.execute("SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid").fetchall()
    expected_rows = [
        (1, UUID('97edb73c-4dac-11e0-9096-0025225356f3'), 20, True),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_can_merge_tracks(conn):
    prepare_database(conn, """
INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (%(fp1)s, %(len1)s, 1, 1), (%(fp2)s, %(len2)s, 2, 1),
           (%(fp3)s, %(len3)s, 3, 1);
    """, dict(fp1=TEST_1A_FP_RAW, len1=TEST_1A_LENGTH,
              fp2=TEST_1B_FP_RAW, len2=TEST_1B_LENGTH,
              fp3=TEST_2_FP_RAW, len3=TEST_2_LENGTH))
    groups = can_merge_tracks(conn, [1, 2, 3])
    assert_equals([set([1, 2])], groups)


@with_database
def test_can_add_fp_to_track(conn):
    prepare_database(conn, """
INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (%(fp1)s, %(len1)s, 1, 1);
    """, dict(fp1=TEST_1A_FP_RAW, len1=TEST_1A_LENGTH))
    res = can_add_fp_to_track(conn, 1, TEST_2_FP_RAW, TEST_2_LENGTH)
    assert_equals(False, res)
    res = can_add_fp_to_track(conn, 1, TEST_1B_FP_RAW, TEST_1B_LENGTH + 20)
    assert_equals(False, res)
    res = can_add_fp_to_track(conn, 1, TEST_1B_FP_RAW, TEST_1B_LENGTH)
    assert_equals(True, res)
