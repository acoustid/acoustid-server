CREATE TABLE meta (
    id serial NOT NULL,
    track varchar,
    artist varchar,
    album varchar,
    album_artist varchar,
    track_no int,
    disc_no int,
    year int
);

ALTER TABLE meta ADD CONSTRAINT meta_pkey PRIMARY KEY (id);
ALTER TABLE submission ADD meta_id int;
ALTER TABLE fingerprint ADD meta_id int;

ALTER TABLE submission ADD CONSTRAINT submission_fk_meta_id
    FOREIGN KEY (meta_id) REFERENCES meta (id);
ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_meta_id
    FOREIGN KEY (meta_id) REFERENCES meta (id);

