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

CREATE TABLE track_mbid_source (
    id serial NOT NULL,
    track_mbid_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

ALTER TABLE track_mbid_source ADD CONSTRAINT track_mbid_source_fk_track_mbid_id
    FOREIGN KEY (track_mbid_id)
    REFERENCES track_mbid (id);

ALTER TABLE track_mbid_source ADD CONSTRAINT track_mbid_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_mbid_source ADD CONSTRAINT track_mbid_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE track_mbid_source ADD CONSTRAINT track_mbid_source_pkey PRIMARY KEY (id);


CREATE TABLE track_puid_source (
    id serial NOT NULL,
    track_puid_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

ALTER TABLE track_puid_source ADD CONSTRAINT track_puid_source_fk_track_puid_id
    FOREIGN KEY (track_puid_id)
    REFERENCES track_puid (id);

ALTER TABLE track_puid_source ADD CONSTRAINT track_puid_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_puid_source ADD CONSTRAINT track_puid_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE track_puid_source ADD CONSTRAINT track_puid_source_pkey PRIMARY KEY (id);


CREATE TABLE fingerprint_source (
    id serial NOT NULL,
    fingerprint_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

ALTER TABLE fingerprint_source ADD CONSTRAINT fingerprint_source_fk_fingerprint_id
    FOREIGN KEY (fingerprint_id)
    REFERENCES fingerprint (id);

ALTER TABLE fingerprint_source ADD CONSTRAINT fingerprint_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE fingerprint_source ADD CONSTRAINT fingerprint_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE fingerprint_source ADD CONSTRAINT fingerprint_source_pkey PRIMARY KEY (id);

