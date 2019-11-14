CREATE DATABASE "acoustid_app";
CREATE DATABASE "acoustid_fingerprint";
CREATE DATABASE "acoustid_ingest";
CREATE DATABASE "musicbrainz";

CREATE DATABASE "acoustid_test";

\c acoustid_fingerprint
create extension intarray;
create extension pgcrypto;
create extension acoustid;

\c musicbrainz
create extension pgcrypto;
create extension cube;

\c acoustid_test
create extension intarray;
create extension pgcrypto;
create extension acoustid;
create extension cube;
