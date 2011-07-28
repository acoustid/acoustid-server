ALTER TABLE submission ADD fingerprint_id int;

ALTER TABLE submission ADD CONSTRAINT submission_fk_fingerprint_id
    FOREIGN KEY (fingerprint_id)
    REFERENCES fingerprint (id);

ALTER TABLE fingerprint ADD submission_count int;
ALTER TABLE fingerprint DROP COLUMN submission_id;
ALTER TABLE fingerprint DROP COLUMN source_id;
ALTER TABLE track_mbid ADD submission_count int ;
ALTER TABLE track_mbid DROP COLUMN submission_id;

CREATE TABLE track_puid (
    track_id int NOT NULL,
    puid uuid NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp,
    submission_count int NOT NULL
);
ALTER TABLE track_puid ADD CONSTRAINT track_puid_pkey PRIMARY KEY (track_id, puid);
ALTER TABLE track_puid ADD CONSTRAINT track_puid_fk_track_id FOREIGN KEY (track_id) REFERENCES track (id);
CREATE INDEX track_puid_idx_puid ON track_puid (puid);

ALTER TABLE track ADD new_id int;
ALTER TABLE track ADD CONSTRAINT track_fk_new_id FOREIGN KEY (new_id) REFERENCES track (id);

ALTER TABLE track_mbid ADD id serial NOT NULL;
ALTER TABLE track_puid ADD id serial NOT NULL;
ALTER TABLE track_mbid DROP CONSTRAINT track_mbid_pkey;
ALTER TABLE track_puid DROP CONSTRAINT track_puid_pkey;
ALTER TABLE track_mbid ADD CONSTRAINT track_mbid_pkey PRIMARY KEY (id);
ALTER TABLE track_puid ADD CONSTRAINT track_puid_pkey PRIMARY KEY (id);
CREATE INDEX track_mbid_idx_uniq ON track_mbid (track_id, mbid);
CREATE INDEX track_puid_idx_uniq ON track_puid (track_id, puid);

