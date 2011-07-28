ALTER TABLE account_openid ADD CONSTRAINT account_openid_fk_account_id
    FOREIGN KEY (account_id)
    REFERENCES account (id);

ALTER TABLE source ADD CONSTRAINT source_fk_application_id
    FOREIGN KEY (application_id)
    REFERENCES application (id);

ALTER TABLE source ADD CONSTRAINT source_fk_account_id
    FOREIGN KEY (account_id)
    REFERENCES account (id);

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_format_id
    FOREIGN KEY (format_id)
    REFERENCES format (id);

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE track ADD CONSTRAINT track_fk_new_id
    FOREIGN KEY (new_id)
    REFERENCES track (id);

ALTER TABLE track_mbid ADD CONSTRAINT track_mbid_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE track_mbid ADD CONSTRAINT track_mbid_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_puid ADD CONSTRAINT track_puid_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_format_id
    FOREIGN KEY (format_id)
    REFERENCES format (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_fingerprint_id
    FOREIGN KEY (fingerprint_id)
    REFERENCES fingerprint (id);

ALTER TABLE stats_top_accounts ADD CONSTRAINT stats_top_accounts_fk_account_id
    FOREIGN KEY (account_id)
    REFERENCES account (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_meta_id
    FOREIGN KEY (meta_id) REFERENCES meta (id);

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_meta_id
    FOREIGN KEY (meta_id) REFERENCES meta (id);

