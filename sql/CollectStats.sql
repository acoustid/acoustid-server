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

INSERT INTO stats (name, value) VALUES ('track_mbid.unique', (
    SELECT count(DISTINCT mbid) FROM track_mbid
));

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

DELETE FROM stats_top_accounts;
INSERT INTO stats_top_accounts (account_id, count)
	SELECT account_id, count(*) FROM (
		SELECT so.account_id
		FROM submission su
		JOIN source so ON su.source_id=so.id
		WHERE su.created > now() - INTERVAL '5' DAY
	) a
	GROUP BY account_id;

COMMIT;
