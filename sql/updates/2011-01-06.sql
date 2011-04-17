ALTER TABLE submission ALTER mbid DROP NOT NULL;
ALTER TABLE submission ADD puid uuid;

