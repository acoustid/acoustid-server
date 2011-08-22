ALTER TABLE track_mbid ADD disabled boolean NOT NULL DEFAULT false;

CREATE TABLE track_mbid_change (
    id serial NOT NULL,
    track_mbid_id int NOT NULL,
    account_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

ALTER TABLE track_mbid_change ADD CONSTRAINT track_mbid_change_pkey PRIMARY KEY (id);
ALTER TABLE track_mbid_change ADD CONSTRAINT track_mbid_change_fk_track_mbid_id FOREIGN KEY (track_mbid_id) REFERENCES track_mbid (id);
ALTER TABLE track_mbid_change ADD CONSTRAINT track_mbid_change_fk_account_id FOREIGN KEY (account_id) REFERENCES account (id);

