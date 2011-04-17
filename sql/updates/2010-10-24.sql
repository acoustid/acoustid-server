ALTER TABLE track_mbid ADD created timestamp with time zone DEFAULT current_timestamp;
ALTER TABLE track ADD created timestamp with time zone DEFAULT current_timestamp;

DROP INDEX submission_idx_handled;
CREATE INDEX submission_idx_handled ON submission (id) WHERE handled = false;

