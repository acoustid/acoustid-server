CREATE UNIQUE INDEX account_idx_apikey ON account (apikey);
CREATE UNIQUE INDEX account_idx_mbuser ON account (mbuser);

CREATE INDEX account_openid_idx_account_id ON account_openid (account_id);

CREATE UNIQUE INDEX application_idx_apikey ON application (apikey);

CREATE UNIQUE INDEX format_idx_name ON format (name);

CREATE UNIQUE INDEX source_idx_uniq ON source (application_id, account_id);

CREATE INDEX fingerprint_idx_fingerprint ON fingerprint
    USING gin (extract_fp_query(fingerprint) gin__int_ops);

CREATE INDEX fingerprint_idx_length ON fingerprint (length);
CREATE INDEX fingerprint_idx_track_id ON fingerprint (track_id);
CREATE INDEX fingerprint_idx_hash_query ON fingerprint (hash_query);
CREATE INDEX fingerprint_idx_hash_full ON fingerprint (hash_full);

CREATE INDEX track_mbid_idx_mbid ON track_mbid (mbid);
CREATE INDEX track_puid_idx_puid ON track_puid (puid);

CREATE INDEX stats_idx_date ON stats (date);
CREATE INDEX stats_idx_name_date ON stats (name, date);

CREATE INDEX submission_idx_handled ON submission (id) WHERE handled = false;

