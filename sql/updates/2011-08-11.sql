CREATE TABLE foreignid_vendor (
    id serial NOT NULL,
    name varchar NOT NULL
);

CREATE TABLE foreignid (
    id serial NOT NULL,
    vendor_id int NOT NULL,
    name text NOT NULL
);

CREATE TABLE track_foreignid (
    id serial NOT NULL,
    track_id int NOT NULL,
    foreignid_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp,
    submission_count int NOT NULL
);

CREATE TABLE track_foreignid_source (
    id serial NOT NULL,
    track_foreignid_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

ALTER TABLE foreignid ADD CONSTRAINT foreignid_pkey PRIMARY KEY (id);
ALTER TABLE foreignid_vendor ADD CONSTRAINT foreignid_vendor_pkey PRIMARY KEY (id);
ALTER TABLE track_foreignid ADD CONSTRAINT track_foreignid_pkey PRIMARY KEY (id);
ALTER TABLE track_foreignid_source ADD CONSTRAINT track_foreignid_source_pkey PRIMARY KEY (id);


ALTER TABLE submission ADD foreignid_id int;



ALTER TABLE track_foreignid ADD CONSTRAINT track_foreignid_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE track_foreignid ADD CONSTRAINT track_foreignid_fk_foreignid_id
    FOREIGN KEY (foreignid_id)
    REFERENCES foreignid (id);

ALTER TABLE track_foreignid_source ADD CONSTRAINT track_foreignid_source_fk_track_foreignid_id
    FOREIGN KEY (track_foreignid_id)
    REFERENCES track_foreignid (id);

ALTER TABLE track_foreignid_source ADD CONSTRAINT track_foreignid_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_foreignid_source ADD CONSTRAINT track_foreignid_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);




ALTER TABLE foreignid ADD CONSTRAINT foreignid_fk_vendor_id
    FOREIGN KEY (vendor_id)
    REFERENCES foreignid_vendor (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_foreignid_id
    FOREIGN KEY (foreignid_id)
    REFERENCES foreignid (id);

