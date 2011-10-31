CREATE UNIQUE INDEX account_idx_apikey ON account (apikey);
CREATE UNIQUE INDEX account_idx_mbuser ON account (mbuser);

CREATE INDEX account_openid_idx_account_id ON account_openid (account_id);

CREATE UNIQUE INDEX application_idx_apikey ON application (apikey);

CREATE UNIQUE INDEX foreignid_vendor_idx_name ON foreignid_vendor (name);
CREATE UNIQUE INDEX foreignid_idx_vendor_name ON foreignid (vendor_id, name);

CREATE UNIQUE INDEX format_idx_name ON format (name);

CREATE UNIQUE INDEX source_idx_uniq ON source (application_id, account_id, version);

CREATE INDEX fingerprint_idx_fingerprint ON fingerprint USING gin (acoustid_extract_query(fingerprint) gin__int_ops);

CREATE INDEX fingerprint_idx_length ON fingerprint (length);
CREATE INDEX fingerprint_idx_track_id ON fingerprint (track_id);

CREATE UNIQUE INDEX track_idx_gid ON track (gid);

CREATE INDEX track_mbid_idx_mbid ON track_mbid (mbid);
CREATE INDEX track_mbid_idx_uniq ON track_mbid (track_id, mbid);

CREATE INDEX track_puid_idx_puid ON track_puid (puid);
CREATE INDEX track_puid_idx_uniq ON track_puid (track_id, puid);

CREATE INDEX track_meta_idx_meta_id ON track_meta (meta_id);
CREATE INDEX track_meta_idx_uniq ON track_meta (track_id, meta_id);

CREATE INDEX track_foreignid_idx_foreignid_id ON track_foreignid (foreignid_id);
CREATE INDEX track_foreignid_idx_uniq ON track_foreignid (track_id, foreignid_id);

CREATE INDEX stats_idx_date ON stats (date);
CREATE INDEX stats_idx_name_date ON stats (name, date);

CREATE INDEX submission_idx_handled ON submission (id) WHERE handled = false;

