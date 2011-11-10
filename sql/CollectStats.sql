\set ON_ERROR_STOP 1
BEGIN;

INSERT INTO stats (name, value) VALUES ('account.all', (
    SELECT count(*) FROM account
));

INSERT INTO stats (name, value) VALUES ('account.musicbrainz', (
    SELECT count(*) FROM account WHERE mbuser IS NOT NULL
));

INSERT INTO stats (name, value) VALUES ('account.openid', (
    SELECT count(DISTINCT account_id) FROM account_openid
));

INSERT INTO stats (name, value) VALUES ('application.all', (
    SELECT count(*) FROM application
));

INSERT INTO stats (name, value) VALUES ('format.all', (
    SELECT count(*) FROM format
));

INSERT INTO stats (name, value) VALUES ('fingerprint.all', (
    SELECT count(*) FROM fingerprint
));

INSERT INTO stats (name, value) VALUES ('track_mbid.all', (
    SELECT count(*) FROM track_mbid
));

INSERT INTO stats (name, value) VALUES ('track_puid.all', (
    SELECT count(*) FROM track_puid
));

INSERT INTO stats (name, value) VALUES ('mbid.all', (SELECT count(DISTINCT mbid) FROM track_mbid));
INSERT INTO stats (name, value) VALUES ('puid.all', (SELECT count(DISTINCT puid) FROM track_puid));

INSERT INTO stats (name, value) VALUES ('track.all', (
    SELECT count(*) FROM track
));

SELECT update_account_stats();

INSERT INTO stats (name, value) VALUES ('submission.all', (
    SELECT sum(submission_count) FROM account
));

INSERT INTO stats (name, value) VALUES ('submission.unhandled', (
    SELECT count(*) FROM submission WHERE not handled
));

INSERT INTO stats (name, value) VALUES ('account.active', (
    SELECT count(*) FROM account WHERE submission_count > 0
));

SELECT track_count, count(*) mbid_count
    INTO TEMP TABLE tmp_mbid_tracks
    FROM (
        SELECT count(track_id) track_count FROM track_mbid
        WHERE disabled=false
        GROUP BY mbid
    ) a
    GROUP BY track_count ORDER BY track_count;

INSERT INTO stats (name, value) VALUES ('mbid.0tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=0), 0));
INSERT INTO stats (name, value) VALUES ('mbid.1tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=1), 0));
INSERT INTO stats (name, value) VALUES ('mbid.2tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=2), 0));
INSERT INTO stats (name, value) VALUES ('mbid.3tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=3), 0));
INSERT INTO stats (name, value) VALUES ('mbid.4tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=4), 0));
INSERT INTO stats (name, value) VALUES ('mbid.5tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=5), 0));
INSERT INTO stats (name, value) VALUES ('mbid.6tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=6), 0));
INSERT INTO stats (name, value) VALUES ('mbid.7tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=7), 0));
INSERT INTO stats (name, value) VALUES ('mbid.8tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=8), 0));
INSERT INTO stats (name, value) VALUES ('mbid.9tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count=9), 0));
INSERT INTO stats (name, value) VALUES ('mbid.10tracks', coalesce((SELECT sum(mbid_count) FROM tmp_mbid_tracks WHERE track_count>=10), 0));

SELECT mbid_count, count(*) track_count
    INTO TEMP TABLE tmp_track_mbids
    FROM (
        SELECT count(tm.mbid) mbid_count
        FROM track t LEFT JOIN track_mbid tm ON t.id=tm.track_id AND tm.disabled=false
        GROUP BY t.id
    ) a
    GROUP BY mbid_count ORDER BY mbid_count;

INSERT INTO stats (name, value) VALUES ('track.0mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=0), 0));
INSERT INTO stats (name, value) VALUES ('track.1mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=1), 0));
INSERT INTO stats (name, value) VALUES ('track.2mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=2), 0));
INSERT INTO stats (name, value) VALUES ('track.3mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=3), 0));
INSERT INTO stats (name, value) VALUES ('track.4mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=4), 0));
INSERT INTO stats (name, value) VALUES ('track.5mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=5), 0));
INSERT INTO stats (name, value) VALUES ('track.6mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=6), 0));
INSERT INTO stats (name, value) VALUES ('track.7mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=7), 0));
INSERT INTO stats (name, value) VALUES ('track.8mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=8), 0));
INSERT INTO stats (name, value) VALUES ('track.9mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count=9), 0));
INSERT INTO stats (name, value) VALUES ('track.10mbids', coalesce((SELECT sum(track_count) FROM tmp_track_mbids WHERE mbid_count>=10), 0));

SELECT track_count, count(*) puid_count
    INTO TEMP TABLE tmp_puid_tracks
    FROM (
        SELECT count(track_id) track_count FROM track_puid
        GROUP BY puid
    ) a
    GROUP BY track_count ORDER BY track_count;

INSERT INTO stats (name, value) VALUES ('puid.0tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=0), 0));
INSERT INTO stats (name, value) VALUES ('puid.1tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=1), 0));
INSERT INTO stats (name, value) VALUES ('puid.2tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=2), 0));
INSERT INTO stats (name, value) VALUES ('puid.3tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=3), 0));
INSERT INTO stats (name, value) VALUES ('puid.4tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=4), 0));
INSERT INTO stats (name, value) VALUES ('puid.5tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=5), 0));
INSERT INTO stats (name, value) VALUES ('puid.6tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=6), 0));
INSERT INTO stats (name, value) VALUES ('puid.7tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=7), 0));
INSERT INTO stats (name, value) VALUES ('puid.8tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=8), 0));
INSERT INTO stats (name, value) VALUES ('puid.9tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count=9), 0));
INSERT INTO stats (name, value) VALUES ('puid.10tracks', coalesce((SELECT sum(puid_count) FROM tmp_puid_tracks WHERE track_count>=10), 0));

SELECT puid_count, count(*) track_count
    INTO TEMP TABLE tmp_track_puids
    FROM (
        SELECT count(tm.puid) puid_count
        FROM track t LEFT JOIN track_puid tm ON t.id=tm.track_id
        GROUP BY t.id
    ) a
    GROUP BY puid_count ORDER BY puid_count;

INSERT INTO stats (name, value) VALUES ('track.0puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=0), 0));
INSERT INTO stats (name, value) VALUES ('track.1puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=1), 0));
INSERT INTO stats (name, value) VALUES ('track.2puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=2), 0));
INSERT INTO stats (name, value) VALUES ('track.3puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=3), 0));
INSERT INTO stats (name, value) VALUES ('track.4puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=4), 0));
INSERT INTO stats (name, value) VALUES ('track.5puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=5), 0));
INSERT INTO stats (name, value) VALUES ('track.6puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=6), 0));
INSERT INTO stats (name, value) VALUES ('track.7puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=7), 0));
INSERT INTO stats (name, value) VALUES ('track.8puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=8), 0));
INSERT INTO stats (name, value) VALUES ('track.9puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count=9), 0));
INSERT INTO stats (name, value) VALUES ('track.10puids', coalesce((SELECT sum(track_count) FROM tmp_track_puids WHERE puid_count>=10), 0));

INSERT INTO stats (name, value) VALUES ('mbid.onlyacoustid', (
    select count(distinct mbid) from track_mbid tm join musicbrainz.recording r on r.gid=tm.mbid left join musicbrainz.recording_puid rp on rp.recording=r.id where rp.recording is null
));

INSERT INTO stats (name, value) VALUES ('mbid.onlypuid', (
    select count(distinct r.gid) from musicbrainz.recording r join musicbrainz.recording_puid rp on rp.recording=r.id left join track_mbid tm on tm.mbid=r.gid where tm.mbid is null
));

INSERT INTO stats (name, value) VALUES ('mbid.both', (
    select count(distinct r.gid) from musicbrainz.recording r join musicbrainz.recording_puid rp on rp.recording=r.id join track_mbid tm on tm.mbid=r.gid
));

DELETE FROM stats_top_accounts;
INSERT INTO stats_top_accounts (account_id, count)
	SELECT account_id, count(*) FROM (
		SELECT so.account_id
		FROM submission su
		JOIN source so ON su.source_id=so.id
		WHERE su.created > now() - INTERVAL '14' DAY
	) a
	GROUP BY account_id;

COMMIT;
