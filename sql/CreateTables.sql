CREATE TABLE account (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	apikey VARCHAR NOT NULL, 
	mbuser VARCHAR, 
	anonymous BOOLEAN DEFAULT false, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	lastlogin TIMESTAMP WITH TIME ZONE, 
	submission_count INTEGER DEFAULT 0 NOT NULL, 
	application_id INTEGER, 
	application_version VARCHAR, 
	created_from INET
);
CREATE TABLE account_google (
	google_user_id VARCHAR NOT NULL, 
	account_id INTEGER NOT NULL
);
CREATE TABLE account_openid (
	openid VARCHAR NOT NULL, 
	account_id INTEGER NOT NULL
);
CREATE TABLE account_stats_control (
	id SERIAL NOT NULL, 
	last_updated TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE TABLE acoustid_mb_replication_control (
	id SERIAL NOT NULL, 
	current_schema_sequence INTEGER NOT NULL, 
	current_replication_sequence INTEGER, 
	last_replication_date TIMESTAMP WITH TIME ZONE
);
CREATE TABLE application (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	version VARCHAR NOT NULL, 
	apikey VARCHAR NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	active BOOLEAN DEFAULT true, 
	account_id INTEGER NOT NULL, 
	email VARCHAR, 
	website VARCHAR
);
CREATE TABLE fingerprint (
	id SERIAL NOT NULL, 
	fingerprint INTEGER[] NOT NULL, 
	length SMALLINT NOT NULL CHECK (length>0), 
	bitrate SMALLINT CHECK (bitrate>0), 
	format_id INTEGER, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	track_id INTEGER NOT NULL, 
	submission_count INTEGER NOT NULL
);
CREATE TABLE fingerprint_index_queue (
	fingerprint_id INTEGER NOT NULL
);
CREATE TABLE fingerprint_source (
	id SERIAL NOT NULL, 
	fingerprint_id INTEGER NOT NULL, 
	submission_id INTEGER NOT NULL, 
	source_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE TABLE foreignid (
	id SERIAL NOT NULL, 
	vendor_id INTEGER NOT NULL, 
	name TEXT NOT NULL
);
CREATE TABLE foreignid_vendor (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL
);
CREATE TABLE format (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL
);
CREATE TABLE meta (
	id SERIAL NOT NULL, 
	track VARCHAR, 
	artist VARCHAR, 
	album VARCHAR, 
	album_artist VARCHAR, 
	track_no INTEGER, 
	disc_no INTEGER, 
	year INTEGER
);
CREATE TABLE mirror_queue (
	id SERIAL NOT NULL, 
	txid BIGINT DEFAULT txid_current() NOT NULL, 
	tblname VARCHAR NOT NULL, 
	op CHAR(1) NOT NULL CHECK (op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])), 
	data TEXT NOT NULL
);
CREATE TABLE recording_acoustid (
	id INTEGER NOT NULL, 
	acoustid UUID NOT NULL, 
	recording UUID NOT NULL, 
	disabled BOOLEAN DEFAULT false NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated TIMESTAMP WITH TIME ZONE
);
CREATE TABLE replication_control (
	id SERIAL NOT NULL, 
	current_schema_sequence INTEGER NOT NULL, 
	current_replication_sequence INTEGER, 
	last_replication_date TIMESTAMP WITH TIME ZONE
);
CREATE TABLE source (
	id SERIAL NOT NULL, 
	application_id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	version VARCHAR
);
CREATE TABLE stats (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	date DATE DEFAULT CURRENT_DATE NOT NULL, 
	value INTEGER NOT NULL
);
CREATE TABLE stats_lookups (
	id SERIAL NOT NULL, 
	date DATE NOT NULL, 
	hour INTEGER NOT NULL, 
	application_id INTEGER NOT NULL, 
	count_nohits INTEGER DEFAULT 0 NOT NULL, 
	count_hits INTEGER DEFAULT 0 NOT NULL
);
CREATE TABLE stats_top_accounts (
	id SERIAL NOT NULL, 
	account_id INTEGER NOT NULL, 
	count INTEGER NOT NULL
);
CREATE TABLE stats_user_agents (
	id SERIAL NOT NULL, 
	date DATE NOT NULL, 
	application_id INTEGER NOT NULL, 
	user_agent VARCHAR NOT NULL, 
	ip VARCHAR NOT NULL, 
	count INTEGER DEFAULT 0 NOT NULL
);
CREATE TABLE submission (
	id SERIAL NOT NULL, 
	fingerprint INTEGER[] NOT NULL, 
	length SMALLINT NOT NULL CHECK (length>0), 
	bitrate SMALLINT CHECK (bitrate>0), 
	format_id INTEGER, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	source_id INTEGER NOT NULL, 
	mbid UUID, 
	handled BOOLEAN DEFAULT false, 
	puid UUID, 
	meta_id INTEGER, 
	foreignid_id INTEGER
);
CREATE TABLE track (
	id SERIAL NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	new_id INTEGER, 
	gid UUID NOT NULL
);
CREATE TABLE track_foreignid (
	id SERIAL NOT NULL, 
	track_id INTEGER NOT NULL, 
	foreignid_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	submission_count INTEGER NOT NULL
);
CREATE TABLE track_foreignid_source (
	id SERIAL NOT NULL, 
	track_foreignid_id INTEGER NOT NULL, 
	submission_id INTEGER NOT NULL, 
	source_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE TABLE track_mbid (
	track_id INTEGER NOT NULL, 
	mbid UUID NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	id SERIAL NOT NULL, 
	submission_count INTEGER NOT NULL, 
	disabled BOOLEAN DEFAULT false NOT NULL
);
CREATE TABLE track_mbid_change (
	id SERIAL NOT NULL, 
	track_mbid_id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	disabled BOOLEAN NOT NULL, 
	note TEXT
);
CREATE TABLE track_mbid_flag (
	id SERIAL NOT NULL, 
	track_mbid_id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	handled BOOLEAN DEFAULT false NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE TABLE track_mbid_source (
	id SERIAL NOT NULL, 
	track_mbid_id INTEGER NOT NULL, 
	submission_id INTEGER, 
	source_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE TABLE track_meta (
	id SERIAL NOT NULL, 
	track_id INTEGER NOT NULL, 
	meta_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	submission_count INTEGER NOT NULL
);
CREATE TABLE track_meta_source (
	id SERIAL NOT NULL, 
	track_meta_id INTEGER NOT NULL, 
	submission_id INTEGER NOT NULL, 
	source_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE TABLE track_puid (
	track_id INTEGER NOT NULL, 
	puid UUID NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	id SERIAL NOT NULL, 
	submission_count INTEGER NOT NULL
);
CREATE TABLE track_puid_source (
	id SERIAL NOT NULL, 
	track_puid_id INTEGER NOT NULL, 
	submission_id INTEGER NOT NULL, 
	source_id INTEGER NOT NULL, 
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
