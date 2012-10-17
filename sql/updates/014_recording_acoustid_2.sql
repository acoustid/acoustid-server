CREATE OR REPLACE FUNCTION tr_a_upd_track_mbid() RETURNS trigger AS $$
BEGIN
    IF NEW.track_id != OLD.track_id OR NEW.mbid != OLD.mbid OR NEW.disabled != OLD.disabled THEN
        UPDATE recording_acoustid
            SET acoustid = (SELECT gid FROM track WHERE id=NEW.track_id),
                recording = NEW.mbid,
                disabled = NEW.disabled,
                updated = now()
            WHERE id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

