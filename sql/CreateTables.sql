BEGIN;

CREATE TABLE account (
    id serial NOT NULL,
    name varchar NOT NULL,
    apikey varchar NOT NULL,
    mbuser varchar,
    anonymous boolean DEFAULT false,
    created timestamp with time zone DEFAULT current_timestamp,
    lastlogin timestamp with time zone,
    submission_count int NOT NULL DEFAULT 0
);

CREATE TABLE account_stats_control (
    id serial NOT NULL,
    last_updated timestamp with time zone NOT NULL
);

CREATE TABLE account_openid (
    openid varchar NOT NULL,
    account_id int NOT NULL
);

CREATE TABLE application (
    id serial NOT NULL,
    name varchar NOT NULL,
    version varchar NOT NULL,
    apikey varchar NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp,
    active boolean DEFAULT true,
    account_id int NOT NULL
);

CREATE TABLE format (
    id serial NOT NULL,
    name varchar NOT NULL
);

CREATE TABLE source (
    id serial NOT NULL,
    application_id int NOT NULL,
    account_id int NOT NULL
);

CREATE TABLE fingerprint (
    id serial NOT NULL,
    fingerprint int[] NOT NULL,
    length smallint NOT NULL CHECK (length > 0),
    bitrate smallint CHECK (bitrate > 0),
    format_id int,
    created timestamp with time zone NOT NULL DEFAULT current_timestamp,
    track_id int NOT NULL,
    hash_full bytea,
    hash_query bytea,
    submission_count int NOT NULL
);

CREATE TABLE fingerprint_source (
    id serial NOT NULL,
    fingerprint_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

CREATE TABLE fingerprint_index_queue (
    fingerprint_id int NOT NULL
);

CREATE TABLE track (
    id serial NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp,
    new_id int,
    gid uuid NOT NULL
);

CREATE TABLE track_mbid (
    track_id int NOT NULL,
    mbid uuid NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp,
    id serial NOT NULL,
    submission_count int NOT NULL
);

CREATE TABLE track_mbid_source (
    id serial NOT NULL,
    track_mbid_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

CREATE TABLE track_puid (
    track_id int NOT NULL,
    puid uuid NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp,
    id serial NOT NULL,
    submission_count int NOT NULL
);

CREATE TABLE track_puid_source (
    id serial NOT NULL,
    track_puid_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

CREATE TABLE foreignid_vendor (
    id serial NOT NULL,
    name varchar NOT NULL
);

CREATE TABLE foreignid (
    id serial NOT NULL,
    vendor_id int NOT NULL,
    name text(256) NOT NULL
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

CREATE TABLE track_meta (
    id serial NOT NULL,
    track_id int NOT NULL,
    meta_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp,
    submission_count int NOT NULL
);

CREATE TABLE track_meta_source (
    id serial NOT NULL,
    track_meta_id int NOT NULL,
    submission_id int NOT NULL,
    source_id int NOT NULL,
    created timestamp with time zone DEFAULT current_timestamp
);

CREATE TABLE submission (
    id serial NOT NULL,
    fingerprint int[] NOT NULL,
    length smallint NOT NULL CHECK (length > 0),
    bitrate smallint CHECK (bitrate > 0),
    format_id int,
    created timestamp with time zone NOT NULL DEFAULT current_timestamp,
    source_id int NOT NULL,
    mbid uuid,
    handled boolean DEFAULT false,
    puid uuid,
    meta_id int,
    foreignid_id int
);

CREATE TABLE stats (
    id serial NOT NULL,
    name varchar NOT NULL,
    date date NOT NULL DEFAULT current_date,
    value int NOT NULL
);

CREATE TABLE stats_top_accounts (
    id serial NOT NULL,
    account_id int NOT NULL,
    count int NOT NULL
);

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

COMMIT;

