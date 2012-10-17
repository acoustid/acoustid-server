CREATE TABLE recording_acoustid
(
    id                  INTEGER NOT NULL,
    acoustid            UUID NOT NULL,
    recording           UUID NOT NULL,
    disabled            BOOLEAN NOT NULL DEFAULT false,
    created             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated             TIMESTAMP WITH TIME ZONE
) TABLESPACE pg_default;

ALTER TABLE recording_acoustid ADD CONSTRAINT recording_acoustid_pkey PRIMARY KEY (id);

CREATE UNIQUE INDEX recording_acoustid_idx_uniq ON recording_acoustid (recording, acoustid);
CREATE INDEX recording_acoustid_idx_acoustid ON recording_acoustid (acoustid);

INSERT INTO recording_acoustid (id, acoustid, recording, disabled, created) SELECT tm.id, t.gid, tm.mbid, tm.disabled, tm.created FROM track_mbid tm JOIN track t ON tm.track_id=t.id;

CREATE OR REPLACE FUNCTION tr_a_ins_track_mbid() RETURNS trigger AS $$
BEGIN
    INSERT INTO recording_acoustid (id, acoustid, recording, disabled, created) VALUES
        (NEW.id, (SELECT gid FROM track WHERE id=NEW.track_id), NEW.mbid, NEW.disabled, NEW.created);
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION tr_a_upd_track_mbid() RETURNS trigger AS $$
BEGIN
    UPDATE recording_acoustid
        SET acoustid = (SELECT gid FROM track WHERE id=NEW.track_id),
            recording = NEW.mbid,
            disabled = NEW.disabled,
            updated = now()
        WHERE id = NEW.id;
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION tr_a_del_track_mbid() RETURNS trigger AS $$
BEGIN
    DELETE FROM recording_acoustid WHERE id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE 'plpgsql';

CREATE TRIGGER tr_a_ins_track_mbid AFTER INSERT ON track_mbid
    FOR EACH ROW EXECUTE PROCEDURE tr_a_ins_track_mbid();

CREATE TRIGGER tr_a_upd_track_mbid AFTER UPDATE ON track_mbid
    FOR EACH ROW EXECUTE PROCEDURE tr_a_upd_track_mbid();

CREATE TRIGGER tr_a_del_track_mbid AFTER DELETE ON track_mbid
    FOR EACH ROW EXECUTE PROCEDURE tr_a_del_track_mbid();


CREATE TABLE mirror_queue (
    id SERIAL NOT NULL PRIMARY KEY,
    txid bigint NOT NULL DEFAULT txid_current(),
    tblname varchar NOT NULL,
    op char(1) NOT NULL CHECK (op IN ('I', 'U', 'D')),
    data text NOT NULL   
);

CREATE TRIGGER tr_repl_recording_acoustid AFTER INSERT OR UPDATE OR DELETE ON recording_acoustid
   FOR EACH ROW EXECUTE PROCEDURE logtriga('kvvvvv', '
	INSERT INTO mirror_queue (tblname, op, data)
        VALUES (''recording_acoustid'', $1, $2)
   ');

CREATE TRIGGER tr_repl_acoustid_mb_replication_control AFTER INSERT OR UPDATE OR DELETE ON acoustid_mb_replication_control
   FOR EACH ROW EXECUTE PROCEDURE logtriga('kvvv', '
	INSERT INTO mirror_queue (tblname, op, data)
        VALUES (''acoustid_mb_replication_control'', $1, $2)
   ');

CREATE TABLE acoustid_mb_replication_control
(
    id                              SERIAL,
    current_schema_sequence         INTEGER NOT NULL,
    current_replication_sequence    INTEGER,
    last_replication_date           TIMESTAMP WITH TIME ZONE
);

INSERT INTO acoustid_mb_replication_control (current_schema_sequence, current_replication_sequence, last_replication_date) VALUES (1, 0, NOW());

