#!/usr/bin/env python

# Copyright (C) 2015 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import re
import datetime
import logging
import random
from sqlalchemy import sql, orm
from mbdata.models import Recording
from acoustid.db import DatabaseContext
from acoustid.models import Application, Track, TrackMBID, TrackMBIDSource, TrackMBIDChange, Source, Account
from acoustid.script import run_script

SK_ID = 342

logger = logging.getLogger(__file__)


class NameMatcher(object):

    def __init__(self):
        self.words = {}

    def _iter_words(self, name):
        name = re.sub(r'\s+', '', name.lower())
        return (name[i:i + 4] for i in range(max(1, len(name) - 4 + 1)))

    def add_name(self, name, sources):
        for word in self._iter_words(name):
            if word in self.words:
                self.words[word] += sources
            else:
                self.words[word] = sources

    def finish(self):
        scale = 1.0 / sum(self.words.values())
        for word in self.words.keys():
            self.words[word] *= scale

    def match(self, name):
        score = 0.0
        for word in self._iter_words(name):
            score += self.words.get(word, 0)
        return score


def is_good_match(db, track, mbid):
    track_mbids = db.session.query(TrackMBID, Recording).\
        select_from(TrackMBID).\
        outerjoin(Recording, Recording.gid == TrackMBID.mbid).\
        filter(TrackMBID.track == track, TrackMBID.disabled == False).all()

    track_mbid_sources = db.session.query(TrackMBIDSource).\
        join(TrackMBID).filter(TrackMBID.track_id == track.id).all()

    sources_by_track_mbid = {}
    for track_mbid_source in track_mbid_sources:
        sources_by_track_mbid.setdefault(track_mbid_source.track_mbid_id, set()).add(track_mbid_source.source_id)
    for track_mbid_id in sources_by_track_mbid.keys():
        sources_by_track_mbid[track_mbid_id] = len(sources_by_track_mbid[track_mbid_id])

    top_sources = 0
    matcher = NameMatcher()
    for track_mbid, recording in track_mbids:
        sources = sources_by_track_mbid[track_mbid.id]
        top_sources = max(top_sources, sources)
        if recording is None:
            continue
        matcher.add_name(recording.name, sources)
    matcher.finish()

    for track_mbid, recording in track_mbids:
        if recording is None or track_mbid.mbid != mbid:
            continue
        score = matcher.match(recording.name)
        sources = sources_by_track_mbid[track_mbid.id]
        print "   ", recording.name, score, sources
        if score > 0.5 or sources > top_sources * 0.5:
            return True

    return False


def has_another_good_match(db, mbid, bad_track_id):
    print "  checking for other tracks with MBID", mbid

    tracks = db.session.query(Track).join(TrackMBID).\
        filter(TrackMBID.mbid == mbid, TrackMBID.disabled == False).\
        filter(Track.id != bad_track_id).all()

    for track in tracks:
        print "  MBID", mbid, "is also on", track.gid
        if is_good_match(db, track, mbid):
            return True

    return False


def has_been_manually_enabled(db, track_mbid):
    return db.session.query(TrackMBIDChange).filter_by(track_mbid=track_mbid, disabled=False).count() > 0


def handle_track(db, track):
    track_mbids = db.session.query(TrackMBID, Recording).\
        select_from(TrackMBID).\
        outerjoin(Recording, Recording.gid == TrackMBID.mbid).\
        filter(TrackMBID.track == track, TrackMBID.disabled == False).all()

    if len(track_mbids) < 2:
        return

    print "checking track", track.gid

    track_mbid_sources = db.session.query(TrackMBIDSource).\
        join(TrackMBID).filter(TrackMBID.track_id == track.id).all()

    sources_by_track_mbid = {}
    for track_mbid_source in track_mbid_sources:
        sources_by_track_mbid.setdefault(track_mbid_source.track_mbid_id, set()).add(track_mbid_source.source_id)
    for track_mbid_id in sources_by_track_mbid.keys():
        sources_by_track_mbid[track_mbid_id] = len(sources_by_track_mbid[track_mbid_id])

    top_sources = 0
    matcher = NameMatcher()
    for track_mbid, recording in track_mbids:
        sources = sources_by_track_mbid[track_mbid.id]
        top_sources = max(top_sources, sources)
        if recording is None:
            continue
        matcher.add_name(recording.name, sources)
    matcher.finish()

    for track_mbid, recording in track_mbids:
        if recording is None:
            continue
        score = matcher.match(recording.name)
        sources = sources_by_track_mbid[track_mbid.id]
        print recording.name, score, sources
        if score < 0.2 and sources < top_sources * 0.2 and has_another_good_match(db, track_mbid.mbid, track.id) and not has_been_manually_enabled(db, track_mbid):
            disable_track_mbid(db, track_mbid, '')
            print "  DELETE!"
        else:
            print "  KEEP!"


def disable_track_mbid(db, track_mbid, note):
    track_mbid.disabled = True
    acoustid_bot = db.session.query(Account).filter_by(name='acoustid_bot').one()
    change = TrackMBIDChange()
    change.track_mbid = track_mbid
    change.account = acoustid_bot
    change.disabled = track_mbid.disabled
    change.note = note
    change.created = datetime.datetime.now()
    db.session.add(change)


def main(script, opts, args):
    db = DatabaseContext(script.engine)

    min_track_id = db.session.query(sql.func.min(Track.id)).scalar()
    max_track_id = db.session.query(sql.func.max(Track.id)).scalar()

    track_ids = db.session.query(TrackMBID.track_id).\
        filter(TrackMBID.disabled == False).\
        group_by(TrackMBID.track_id).having(sql.func.count('*') > 10)

    for track_id in track_ids:
        track = db.session.query(Track).get(track_id)
        if track is not None:
            handle_track(db, track)
            db.session.commit()

    while False:
        track_id = random.randint(min_track_id, max_track_id)
        track = db.session.query(Track).get(track_id)
        if track is not None:
            handle_track(db, track)
            db.session.commit()

run_script(main)

