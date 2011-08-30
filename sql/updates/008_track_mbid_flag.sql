CREATE TABLE track_mbid_flag (
    id serial NOT NULL,
    track_mbid_id int NOT NULL,
    account_id int NOT NULL,
    handled boolean NOT NULL DEFAULT false,
    created timestamp with time zone DEFAULT current_timestamp
);

ALTER TABLE track_mbid_flag ADD CONSTRAINT track_mbid_flag_pkey PRIMARY KEY (id);
ALTER TABLE track_mbid_flag ADD CONSTRAINT track_mbid_flag_fk_track_mbid_id FOREIGN KEY (track_mbid_id) REFERENCES track_mbid (id);
ALTER TABLE track_mbid_flag ADD CONSTRAINT track_mbid_flag_fk_account_id FOREIGN KEY (account_id) REFERENCES account (id);

