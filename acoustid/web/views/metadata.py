import logging
from typing import Any

from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from sqlalchemy import sql
from sqlalchemy.orm import load_only

from acoustid import tables as schema
from acoustid.data.account import is_moderator
from acoustid.data.musicbrainz import lookup_recording_metadata
from acoustid.data.track import resolve_track_gid
from acoustid.models import Account, Meta, TrackMBID, TrackMBIDChange, TrackMeta
from acoustid.utils import is_uuid
from acoustid.web import db
from acoustid.web.utils import require_user

logger = logging.getLogger(__name__)

metadata_page = Blueprint("metadata", __name__)


@metadata_page.route("/track/<track_id_or_gid>")
def track(track_id_or_gid):
    fingerprint_db = db.get_fingerprint_db()
    musicbrainz_db = db.get_musicbrainz_db()

    show_disabled = request.args.get("disabled") == "1"

    if is_uuid(track_id_or_gid):
        track_gid = track_id_or_gid
        track_id = resolve_track_gid(fingerprint_db, track_gid)
    else:
        try:
            track_id = int(track_id_or_gid)
        except ValueError:
            track_id = None
        query = sql.select([schema.track.c.gid], schema.track.c.id == track_id)
        track_gid = fingerprint_db.execute(query).scalar()

    if track_id is None or track_gid is None:
        abort(404)

    title = 'Track "%s"' % (track_gid,)
    track = {"id": track_id, "gid": track_gid}

    query = sql.select(
        [
            schema.fingerprint.c.id,
            schema.fingerprint.c.length,
            schema.fingerprint.c.submission_count,
        ],
        schema.fingerprint.c.track_id == track_id,
    ).order_by(schema.fingerprint.c.length)
    fingerprints = fingerprint_db.execute(query).fetchall()

    query = sql.select(
        [
            schema.track_mbid.c.id,
            schema.track_mbid.c.mbid,
            schema.track_mbid.c.submission_count,
            schema.track_mbid.c.disabled,
        ],
        schema.track_mbid.c.track_id == track_id,
    )
    mbids = fingerprint_db.execute(query).fetchall()

    metadata = lookup_recording_metadata(musicbrainz_db, [r["mbid"] for r in mbids])

    num_disabled = 0
    num_enabled = 0

    recordings = []
    for mbid in mbids:
        recording = metadata.get(mbid["mbid"], {})
        recording["mbid"] = mbid["mbid"]
        recording["submission_count"] = mbid["submission_count"]
        recording["disabled"] = mbid["disabled"]
        if recording["disabled"]:
            num_disabled += 1
        else:
            num_enabled += 1
        recordings.append(recording)
    recordings.sort(key=lambda r: r.get("name", r.get("mbid")))

    user_metadata = (
        db.session.query(
            Meta.track,
            Meta.artist,
            Meta.album,
            sql.func.sum(TrackMeta.submission_count),
        )
        .select_from(TrackMeta)
        .join(Meta)
        .filter(TrackMeta.track_id == track_id)
        .group_by(Meta.track, Meta.artist, Meta.album)
        .order_by(sql.func.min(TrackMeta.created))
        .all()
    )

    edits = (
        db.session.query(TrackMBIDChange)
        .filter(TrackMBIDChange.track_mbid_id.in_(m.id for m in mbids))
        .order_by(TrackMBIDChange.created.desc())
        .all()
    )

    edits_accounts = (
        db.session.query(Account)
        .options(load_only("mbuser", "name"))
        .filter(Account.id.in_(e.account_id for e in edits))
        .all()
    )
    edits_accounts_by_id = {}
    for account in edits_accounts:
        edits_accounts_by_id[account.id] = account

    edits_track_mbids = (
        db.session.query(TrackMBID)
        .options(load_only("mbid"))
        .filter(TrackMBID.id.in_(e.track_mbid_id for e in edits))
        .all()
    )
    edits_track_mbids_by_id = {}
    for track_mbid in edits_track_mbids:
        edits_track_mbids_by_id[track_mbid.id] = track_mbid

    for edit in edits:
        account = edits_accounts_by_id.get(edit.account_id)
        if account is not None:
            edit.account = account
        track_mbid = edits_track_mbids_by_id.get(edit.track_mbid_id)
        if track_mbid is not None:
            edit.track_mbid = track_mbid

    moderator = is_moderator(db.get_app_db(), session.get("id"))

    return render_template(
        "track.html",
        title=title,
        fingerprints=fingerprints,
        recordings=recordings,
        moderator=moderator,
        track=track,
        edits=edits,
        user_metadata=user_metadata,
        show_disabled=show_disabled,
        num_disabled=num_disabled,
        num_enabled=num_enabled,
    )


@metadata_page.route("/fingerprint/<int:fingerprint_id>")
def fingerprint(fingerprint_id):
    finerprint_db = db.get_fingerprint_db()
    title = "Fingerprint #%s" % (fingerprint_id,)
    query = sql.select(
        [
            schema.fingerprint.c.id,
            schema.fingerprint.c.length,
            schema.fingerprint.c.fingerprint,
            schema.fingerprint.c.track_id,
            schema.fingerprint.c.submission_count,
        ],
        schema.fingerprint.c.id == fingerprint_id,
    )
    fingerprint = finerprint_db.execute(query).first()
    query = sql.select(
        [schema.track.c.gid], schema.track.c.id == fingerprint["track_id"]
    )
    track_gid = finerprint_db.execute(query).scalar()
    return render_template(
        "fingerprint.html", title=title, fingerprint=fingerprint, track_gid=track_gid
    )


@metadata_page.route(
    "/fingerprint/<int:fingerprint_id_1>/compare/<int:fingerprint_id_2>"
)
def compare_fingerprints(fingerprint_id_1, fingerprint_id_2):
    finerprint_db = db.get_fingerprint_db()
    title = "Compare fingerprints #%s and #%s" % (fingerprint_id_1, fingerprint_id_2)
    query = sql.select(
        [
            schema.fingerprint.c.id,
            schema.fingerprint.c.length,
            schema.fingerprint.c.fingerprint,
            schema.fingerprint.c.track_id,
            schema.fingerprint.c.submission_count,
        ],
        schema.fingerprint.c.id.in_((fingerprint_id_1, fingerprint_id_2)),
    )
    fingerprint_1 = None
    fingerprint_2 = None
    for fingerprint in finerprint_db.execute(query):
        if fingerprint["id"] == fingerprint_id_1:
            fingerprint_1 = fingerprint
        elif fingerprint["id"] == fingerprint_id_2:
            fingerprint_2 = fingerprint
    if not fingerprint_1 or not fingerprint_2:
        abort(404)
    return render_template(
        "compare_fingerprints.html",
        title=title,
        fingerprint_1=fingerprint_1,
        fingerprint_2=fingerprint_2,
    )


@metadata_page.route("/mbid/<mbid>")
def mbid(mbid):
    from acoustid.data.musicbrainz import lookup_recording_metadata
    from acoustid.data.track import lookup_tracks

    metadata = lookup_recording_metadata(db.get_musicbrainz_db(), [mbid])
    if mbid not in metadata:
        title = "Incorrect Recording"
        return render_template("mbid-not-found.html", title=title, mbid=mbid)
    metadata = metadata[mbid]
    title = 'Recording "%s" by %s' % (metadata["name"], metadata["artist_name"])
    tracks = lookup_tracks(db.get_fingerprint_db(), [mbid]).get(mbid, [])
    return render_template("mbid.html", title=title, tracks=tracks, mbid=mbid)


@metadata_page.route("/edit/toggle-track-mbid", methods=["GET", "POST"])
def toggle_track_mbid():
    fingerprint_db = db.get_fingerprint_db()
    ingest_db = db.get_ingest_db()
    app_db = db.get_app_db()
    user = require_user()
    track_id = request.values.get("track_id", type=int)
    if track_id:
        query = sql.select([schema.track.c.gid], schema.track.c.id == track_id)
        track_gid = fingerprint_db.execute(query).scalar()
    else:
        track_gid = request.values.get("track_gid")
        track_id = resolve_track_gid(fingerprint_db, track_gid)
    state = bool(request.values.get("state", type=int))
    mbid = request.values.get("mbid")
    if not track_id or not mbid or not track_gid:
        return redirect(url_for("general.index"))
    if not is_moderator(app_db, user.id):
        title = "MusicBrainz account required"
        return render_template("toggle_track_mbid_login.html", title=title)
    query = sql.select(
        [schema.track_mbid.c.id, schema.track_mbid.c.disabled],
        sql.and_(
            schema.track_mbid.c.track_id == track_id, schema.track_mbid.c.mbid == mbid
        ),
    )
    rows = fingerprint_db.execute(query).fetchall()
    if not rows:
        return redirect(url_for("general.index"))
    id, current_state = rows[0]
    if state == current_state:
        return redirect(url_for(".track", track_id_or_gid=track_id))
    if request.form.get("submit"):
        note = request.values.get("note")
        update_stmt = (
            schema.track_mbid.update()
            .where(schema.track_mbid.c.id == id)
            .values(disabled=state)
        )
        fingerprint_db.execute(update_stmt)
        insert_stmt = schema.track_mbid_change.insert().values(
            track_mbid_id=id, account_id=session["id"], disabled=state, note=note
        )
        ingest_db.execute(insert_stmt)
        db.session.commit()
        return redirect(url_for(".track", track_id_or_gid=track_id))
    if state:
        title = "Unlink MBID"
    else:
        title = "Link MBID"
    return render_template(
        "toggle_track_mbid.html",
        title=title,
        track_gid=track_gid,
        mbid=mbid,
        state=state,
        track_id=track_id,
    )
