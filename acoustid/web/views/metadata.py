import logging
from typing import Any

from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from sqlalchemy import sql
from sqlalchemy.orm import load_only
from werkzeug.wrappers.response import Response

from acoustid import const
from acoustid import tables as schema
from acoustid.data.account import is_moderator
from acoustid.data.musicbrainz import lookup_recording_metadata
from acoustid.data.track import (
    calculate_fingerprint_similarity_matrix,
    resolve_track_gid,
)
from acoustid.models import Account, Meta, TrackMBID, TrackMBIDChange, TrackMeta
from acoustid.utils import is_uuid
from acoustid.web import db
from acoustid.web.grouping import MetaRow, group_metadata
from acoustid.web.utils import require_user

logger = logging.getLogger(__name__)

metadata_page = Blueprint("metadata", __name__)

# Fingerprint drawings put the raw fingerprints into the page, so only the
# most submitted fingerprints (on the recording page, AcoustIDs) get one. The
# similarity grid compares every pair, so it is left out for tracks with many
# fingerprints. The drawings only show the first two minutes.
MAX_FINGERPRINT_THUMBNAILS = 50
THUMBNAIL_FRAMES = 948
MAX_SIMILARITY_MATRIX = 12
# The fingerprint page scores every other fingerprint of the track to rank
# them, which is only done for tracks up to this size.
MAX_RANKED_FINGERPRINTS = 200


@metadata_page.route("/track/<track_id_or_gid>")
def track(track_id_or_gid: str) -> str:
    fingerprint_db = db.get_fingerprint_db()
    musicbrainz_db = db.get_musicbrainz_db()

    show_disabled = request.args.get("disabled") == "1"

    track_gid: str | None = None
    track_id: int | None = None

    if is_uuid(track_id_or_gid):
        track_gid = track_id_or_gid
        track_id = resolve_track_gid(fingerprint_db, track_gid)
    else:
        try:
            track_id = int(track_id_or_gid)
        except ValueError:
            track_id = None
        else:
            query = sql.select(schema.track.c.gid).where(schema.track.c.id == track_id)
            track_gid = fingerprint_db.execute(query).scalar_one_or_none()

    if track_id is None or track_gid is None:
        abort(
            404,
            description="There is no track with ID %s in the AcoustID database."
            % (track_id_or_gid,),
        )

    title = 'Track "%s"' % (track_gid,)
    track = {"id": track_id, "gid": track_gid}

    # Most submitted first, so A is the most common one, as on the recording
    # page.
    query = (
        sql.select(
            schema.fingerprint.c.id,
            schema.fingerprint.c.length,
            schema.fingerprint.c.submission_count,
        )
        .where(schema.fingerprint.c.track_id == track_id)
        .order_by(schema.fingerprint.c.submission_count.desc(), schema.fingerprint.c.id)
    )
    fingerprints = fingerprint_db.execute(query).fetchall()

    fingerprint_data: dict[int, list[int]] = {}
    thumbnail_ids = [fp.id for fp in fingerprints[:MAX_FINGERPRINT_THUMBNAILS]]
    if thumbnail_ids:
        query = sql.select(
            schema.fingerprint.c.id,
            schema.fingerprint.c.fingerprint[1:THUMBNAIL_FRAMES].label("fingerprint"),
        ).where(schema.fingerprint.c.id.in_(thumbnail_ids))
        for row in fingerprint_db.execute(query):
            fingerprint_data[row.id] = row.fingerprint

    similarity: dict[int, dict[int, float]] = {}
    if 2 <= len(fingerprints) <= MAX_SIMILARITY_MATRIX:
        similarity = calculate_fingerprint_similarity_matrix(fingerprint_db, [track_id])

    query = sql.select(
        schema.track_mbid.c.id,
        schema.track_mbid.c.mbid,
        schema.track_mbid.c.submission_count,
        schema.track_mbid.c.disabled,
    ).where(
        schema.track_mbid.c.track_id == track_id,
    )
    mbids = fingerprint_db.execute(query).fetchall()

    metadata = lookup_recording_metadata(musicbrainz_db, [r.mbid for r in mbids])

    num_disabled = 0
    num_enabled = 0

    recordings = []
    for mbid in mbids:
        recording = metadata.get(mbid.mbid, {})
        recording["mbid"] = str(mbid.mbid)
        recording["submission_count"] = mbid.submission_count
        recording["disabled"] = mbid.disabled
        if mbid.disabled:
            num_disabled += 1
        else:
            num_enabled += 1
        recordings.append(recording)
    recordings.sort(key=lambda r: r.get("name", r.get("mbid", "")))
    main_recording = max(
        (r for r in recordings if not r["disabled"] and r.get("name")),
        key=lambda r: r["submission_count"],
        default=None,
    )
    if main_recording is not None:
        title = main_recording["name"]

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
    metadata_mode = "raw" if request.args.get("metadata") == "raw" else "grouped"
    metadata_rows = [
        MetaRow(title or "", artist or "", album or "", int(count or 0))
        for title, artist, album, count in user_metadata
    ]
    metadata_groups = group_metadata(metadata_rows)

    edits = (
        db.session.query(TrackMBIDChange)
        .filter(TrackMBIDChange.track_mbid_id.in_(m.id for m in mbids))
        .order_by(TrackMBIDChange.created.desc())
        .all()
    )

    edits_accounts = (
        db.session.query(Account)
        .options(load_only(Account.mbuser, Account.name))
        .filter(Account.id.in_(e.account_id for e in edits))
        .all()
    )
    edits_accounts_by_id = {}
    for account in edits_accounts:
        edits_accounts_by_id[account.id] = account

    edits_track_mbids = (
        db.session.query(TrackMBID)
        .options(load_only(TrackMBID.mbid))
        .filter(TrackMBID.id.in_(e.track_mbid_id for e in edits))
        .all()
    )
    edits_track_mbids_by_id = {}
    for track_mbid in edits_track_mbids:
        edits_track_mbids_by_id[track_mbid.id] = track_mbid

    for edit in edits:
        account_or_none = edits_accounts_by_id.get(edit.account_id)
        if account_or_none is not None:
            edit.account = account_or_none
        track_mbid_or_none = edits_track_mbids_by_id.get(edit.track_mbid_id)
        if track_mbid_or_none is not None:
            edit.track_mbid = track_mbid_or_none

    current_account_id = session.get("id")
    if current_account_id is None:
        moderator = False
    else:
        moderator = is_moderator(db.get_app_db(), current_account_id)

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
        main_recording=main_recording,
        fingerprint_data=fingerprint_data,
        similarity=similarity,
        metadata_mode=metadata_mode,
        metadata_rows=metadata_rows,
        metadata_groups=metadata_groups,
        thumbnail_frames=THUMBNAIL_FRAMES,
        max_thumbnails=MAX_FINGERPRINT_THUMBNAILS,
    )


def find_track_fingerprints(
    fingerprint_db,
    track_id: int,
    compare_with=None,
    order_by_sources: bool = False,
    limit: int = 50,
):
    """Fingerprints of a track, scored against `compare_with` when given, best first.

    Without `compare_with`, they are ordered by length, or by the number of
    submissions with `order_by_sources`.
    """
    columns = [
        schema.fingerprint.c.id,
        schema.fingerprint.c.length,
        schema.fingerprint.c.submission_count,
    ]
    if compare_with is not None:
        score = sql.func.acoustid_compare2(
            schema.fingerprint.c.fingerprint, compare_with, const.TRACK_MAX_OFFSET
        ).label("score")
        query = sql.select(*columns, score).order_by(score.desc())
    elif order_by_sources:
        query = sql.select(*columns).order_by(
            schema.fingerprint.c.submission_count.desc()
        )
    else:
        query = sql.select(*columns).order_by(schema.fingerprint.c.length)
    query = query.where(schema.fingerprint.c.track_id == track_id).limit(limit)
    return [dict(row._mapping) for row in fingerprint_db.execute(query)]


@metadata_page.route("/fingerprint/<int:fingerprint_id>")
def fingerprint(fingerprint_id: int) -> str:
    fingerprint_db = db.get_fingerprint_db()
    title = "Fingerprint #%s" % (fingerprint_id,)

    query = sql.select(
        schema.fingerprint.c.id,
        schema.fingerprint.c.length,
        schema.fingerprint.c.fingerprint,
        schema.fingerprint.c.track_id,
        schema.fingerprint.c.submission_count,
    ).where(
        schema.fingerprint.c.id == fingerprint_id,
    )
    fingerprint_row = fingerprint_db.execute(query).one_or_none()
    if fingerprint_row is None:
        abort(
            404,
            description="There is no fingerprint #%d in the AcoustID database."
            % (fingerprint_id,),
        )
    fingerprint = dict(fingerprint_row._mapping)

    query = sql.select(schema.track.c.gid).where(
        schema.track.c.id == fingerprint["track_id"]
    )
    track_gid = fingerprint_db.execute(query).scalar_one_or_none()
    if track_gid is None:
        abort(
            404,
            description="Fingerprint #%d doesn't belong to any track."
            % (fingerprint_id,),
        )

    track_size = fingerprint_db.execute(
        sql.select(sql.func.count()).where(
            schema.fingerprint.c.track_id == fingerprint["track_id"]
        )
    ).scalar_one()
    ranked = track_size <= MAX_RANKED_FINGERPRINTS
    siblings = [
        fp
        for fp in find_track_fingerprints(
            fingerprint_db,
            fingerprint["track_id"],
            compare_with=fingerprint["fingerprint"] if ranked else None,
            order_by_sources=not ranked,
        )
        if fp["id"] != fingerprint_id
    ]

    return render_template(
        "fingerprint.html",
        title=title,
        fingerprint=fingerprint,
        track_gid=track_gid,
        siblings=siblings,
        ranked=ranked,
        track_size=track_size,
    )


@metadata_page.route(
    "/fingerprint/<int:fingerprint_id_1>/compare/<int:fingerprint_id_2>"
)
def compare_fingerprints(fingerprint_id_1: int, fingerprint_id_2: int) -> str:
    fingerprint_db = db.get_fingerprint_db()
    title = "Compare #%s and #%s" % (fingerprint_id_1, fingerprint_id_2)
    query = sql.select(
        schema.fingerprint.c.id,
        schema.fingerprint.c.length,
        schema.fingerprint.c.fingerprint,
        schema.fingerprint.c.track_id,
        schema.fingerprint.c.submission_count,
    ).where(
        schema.fingerprint.c.id.in_((fingerprint_id_1, fingerprint_id_2)),
    )
    fingerprint_1: dict[str, Any] | None = None
    fingerprint_2: dict[str, Any] | None = None
    for fingerprint in fingerprint_db.execute(query):
        if fingerprint.id == fingerprint_id_1:
            fingerprint_1 = dict(fingerprint._mapping)
        if fingerprint.id == fingerprint_id_2:
            fingerprint_2 = dict(fingerprint._mapping)
    if not fingerprint_1 or not fingerprint_2:
        missing = fingerprint_id_2 if fingerprint_1 else fingerprint_id_1
        abort(
            404,
            description="There is no fingerprint #%d in the AcoustID database."
            % (missing,),
        )

    # The score from the matcher the service uses, next to the bit error
    # rate the page computes itself.
    matcher_score = fingerprint_db.execute(
        sql.select(
            sql.func.acoustid_compare2(
                fingerprint_1["fingerprint"],
                fingerprint_2["fingerprint"],
                const.TRACK_MAX_OFFSET,
            )
        )
    ).scalar()

    # Offer the other fingerprints of both tracks in the pickers.
    choices: dict[int, dict[str, Any]] = {}
    for fp in (fingerprint_1, fingerprint_2):
        for choice in find_track_fingerprints(fingerprint_db, fp["track_id"]):
            choice["same_track"] = fp["track_id"] == fingerprint_1["track_id"]
            choices.setdefault(choice["id"], choice)
        choices.setdefault(
            fp["id"],
            {
                "id": fp["id"],
                "length": fp["length"],
                "same_track": fp["track_id"] == fingerprint_1["track_id"],
            },
        )

    return render_template(
        "compare_fingerprints.html",
        title=title,
        fingerprint_1=fingerprint_1,
        fingerprint_2=fingerprint_2,
        matcher_score=matcher_score,
        choices=sorted(choices.values(), key=lambda c: (not c["same_track"], c["id"])),
    )


@metadata_page.route("/mbid/<mbid>")
def mbid(mbid: str) -> str:
    if not is_uuid(mbid):
        abort(404, description="%s is not a MusicBrainz recording ID." % (mbid,))
    mbid = mbid.lower()
    fingerprint_db = db.get_fingerprint_db()
    musicbrainz_db = db.get_musicbrainz_db()
    show_disabled = request.args.get("disabled") == "1"

    # The lookups key their results by UUID objects, not strings.
    metadata = {
        str(k): v for k, v in lookup_recording_metadata(musicbrainz_db, [mbid]).items()
    }
    if mbid not in metadata:
        abort(
            404,
            description="There is no MusicBrainz recording with ID %s." % (mbid,),
        )
    recording = metadata[mbid]
    title = "%s by %s" % (recording["name"], recording["artist_name"])

    # The AcoustIDs linked to the recording, most submitted first.
    query = (
        sql.select(
            schema.track.c.id,
            schema.track.c.gid,
            schema.track_mbid.c.submission_count,
            schema.track_mbid.c.disabled,
        )
        .select_from(
            schema.track_mbid.join(
                schema.track, schema.track.c.id == schema.track_mbid.c.track_id
            )
        )
        .where(schema.track_mbid.c.mbid == mbid)
        .order_by(schema.track_mbid.c.submission_count.desc())
    )
    all_tracks = [
        dict(row._mapping, gid=str(row.gid)) for row in fingerprint_db.execute(query)
    ]
    num_disabled = sum(1 for t in all_tracks if t["disabled"])
    tracks = [t for t in all_tracks if show_disabled or not t["disabled"]]
    track_ids = [t["id"] for t in tracks]
    tracks_by_id = {t["id"]: t for t in tracks}
    for t in tracks:
        t.update(fingerprints=0, min_length=None, max_length=None, other_recordings=[])

    # Their fingerprints: how many, and the range of file lengths.
    if track_ids:
        query = (
            sql.select(
                schema.fingerprint.c.track_id,
                sql.func.count().label("fingerprints"),
                sql.func.min(schema.fingerprint.c.length).label("min_length"),
                sql.func.max(schema.fingerprint.c.length).label("max_length"),
            )
            .where(schema.fingerprint.c.track_id.in_(track_ids))
            .group_by(schema.fingerprint.c.track_id)
        )
        for row in fingerprint_db.execute(query):
            tracks_by_id[row.track_id].update(row._mapping)

    # Other recordings the same AcoustIDs are linked to, which is where wrong
    # links show up.
    if track_ids:
        query = (
            sql.select(
                schema.track_mbid.c.track_id,
                schema.track_mbid.c.mbid,
                schema.track_mbid.c.submission_count,
            )
            .where(
                schema.track_mbid.c.track_id.in_(track_ids),
                schema.track_mbid.c.mbid != mbid,
                schema.track_mbid.c.disabled.is_(False),
            )
            .order_by(schema.track_mbid.c.submission_count.desc())
        )
        others: dict[int, list[tuple[str, int]]] = {}
        for row in fingerprint_db.execute(query):
            others.setdefault(row.track_id, []).append(
                (str(row.mbid), row.submission_count)
            )
        other_metadata = {
            str(k): v
            for k, v in lookup_recording_metadata(
                musicbrainz_db, sorted({m for ms in others.values() for m, _ in ms})
            ).items()
        }
        for t in tracks:
            t["other_recordings"] = [
                dict(other_metadata.get(m, {}), mbid=m, submission_count=count)
                for m, count in others.get(t["id"], [])
            ]

    # The most submitted fingerprint of each of the most submitted AcoustIDs,
    # drawn as a thumbnail and compared in the similarity grid.
    representative: dict[int, dict[str, Any]] = {}
    if track_ids:
        query = (
            sql.select(
                schema.fingerprint.c.track_id,
                schema.fingerprint.c.id,
                schema.fingerprint.c.fingerprint[1:THUMBNAIL_FRAMES].label(
                    "fingerprint"
                ),
            )
            .where(
                schema.fingerprint.c.track_id.in_(
                    track_ids[:MAX_FINGERPRINT_THUMBNAILS]
                )
            )
            .distinct(schema.fingerprint.c.track_id)
            .order_by(
                schema.fingerprint.c.track_id,
                schema.fingerprint.c.submission_count.desc(),
            )
        )
        for row in fingerprint_db.execute(query):
            representative[row.track_id] = dict(row._mapping)

    similarity: dict[int, dict[int, float]] = {}
    if 2 <= len(representative) <= MAX_SIMILARITY_MATRIX:
        fp_ids = [r["id"] for r in representative.values()]
        fp1 = schema.fingerprint.alias("fp1")
        fp2 = schema.fingerprint.alias("fp2")
        query = (
            sql.select(
                fp1.c.track_id,
                fp2.c.track_id,
                sql.func.acoustid_compare2(
                    fp1.c.fingerprint, fp2.c.fingerprint, const.TRACK_MAX_OFFSET
                ),
            )
            .select_from(fp1.join(fp2, fp1.c.id < fp2.c.id))
            .where(fp1.c.id.in_(fp_ids), fp2.c.id.in_(fp_ids))
        )
        for track1, track2, score in fingerprint_db.execute(query):
            similarity.setdefault(track1, {})[track2] = score
            similarity.setdefault(track2, {})[track1] = score

    return render_template(
        "mbid.html",
        title=title,
        mbid=mbid,
        recording=recording,
        tracks=tracks,
        num_disabled=num_disabled,
        show_disabled=show_disabled,
        representative=representative,
        similarity=similarity,
        thumbnail_frames=THUMBNAIL_FRAMES,
        max_thumbnails=MAX_FINGERPRINT_THUMBNAILS,
    )


@metadata_page.route("/edit/toggle-track-mbid", methods=["GET", "POST"])
def toggle_track_mbid() -> str | Response:
    fingerprint_db = db.get_fingerprint_db()
    ingest_db = db.get_ingest_db()
    app_db = db.get_app_db()
    user = require_user()
    track_id = request.values.get("track_id", type=int)
    if track_id:
        query = sql.select(schema.track.c.gid).where(schema.track.c.id == track_id)
        track_gid = fingerprint_db.execute(query).scalar_one()
    else:
        track_gid = request.values.get("track_gid")
        if not track_gid:
            abort(404)
        track_id = resolve_track_gid(fingerprint_db, track_gid)
    state = bool(request.values.get("state", type=int))
    mbid = request.values.get("mbid")
    if not track_id or not mbid or not track_gid:
        return redirect(url_for("general.index"))
    if not is_moderator(app_db, user.id):
        title = "MusicBrainz account required"
        return render_template("toggle_track_mbid_login.html", title=title)
    query = sql.select(schema.track_mbid.c.id, schema.track_mbid.c.disabled).where(
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
        title = "Unlink recording"
    else:
        title = "Link recording"
    recording = {
        str(k): v
        for k, v in lookup_recording_metadata(db.get_musicbrainz_db(), [mbid]).items()
    }.get(mbid)
    return render_template(
        "toggle_track_mbid.html",
        title=title,
        track_gid=track_gid,
        mbid=mbid,
        recording=recording,
        state=state,
        track_id=track_id,
    )
