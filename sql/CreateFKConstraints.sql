ALTER TABLE account ADD CONSTRAINT account_fk_application_id
    FOREIGN KEY (application_id)
    REFERENCES application (id);

ALTER TABLE account_openid ADD CONSTRAINT account_openid_fk_account_id
    FOREIGN KEY (account_id)
    REFERENCES account (id);

ALTER TABLE source ADD CONSTRAINT source_fk_application_id
    FOREIGN KEY (application_id)
    REFERENCES application (id);

ALTER TABLE source ADD CONSTRAINT source_fk_account_id
    FOREIGN KEY (account_id)
    REFERENCES account (id);

ALTER TABLE foreignid ADD CONSTRAINT foreignid_fk_vendor_id
    FOREIGN KEY (vendor_id)
    REFERENCES foreignid_vendor (id);

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_format_id
    FOREIGN KEY (format_id)
    REFERENCES format (id);

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE fingerprint_source ADD CONSTRAINT fingerprint_source_fk_fingerprint_id
    FOREIGN KEY (fingerprint_id)
    REFERENCES fingerprint (id);

ALTER TABLE fingerprint_source ADD CONSTRAINT fingerprint_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE fingerprint_source ADD CONSTRAINT fingerprint_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE track ADD CONSTRAINT track_fk_new_id
    FOREIGN KEY (new_id)
    REFERENCES track (id);

ALTER TABLE track_mbid ADD CONSTRAINT track_mbid_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE track_mbid_source ADD CONSTRAINT track_mbid_source_fk_track_mbid_id
    FOREIGN KEY (track_mbid_id)
    REFERENCES track_mbid (id);

ALTER TABLE track_mbid_source ADD CONSTRAINT track_mbid_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_mbid_source ADD CONSTRAINT track_mbid_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE track_puid ADD CONSTRAINT track_puid_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE track_puid_source ADD CONSTRAINT track_puid_source_fk_track_puid_id
    FOREIGN KEY (track_puid_id)
    REFERENCES track_puid (id);

ALTER TABLE track_puid_source ADD CONSTRAINT track_puid_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_puid_source ADD CONSTRAINT track_puid_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);



ALTER TABLE track_foreignid ADD CONSTRAINT track_foreignid_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE track_foreignid ADD CONSTRAINT track_foreignid_fk_foreignid_id
    FOREIGN KEY (foreignid_id)
    REFERENCES foreignid (id);

ALTER TABLE track_foreignid_source ADD CONSTRAINT track_foreignid_source_fk_track_foreignid_id
    FOREIGN KEY (track_foreignid_id)
    REFERENCES track_foreignid (id);

ALTER TABLE track_foreignid_source ADD CONSTRAINT track_foreignid_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_foreignid_source ADD CONSTRAINT track_foreignid_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);



ALTER TABLE track_meta ADD CONSTRAINT track_meta_fk_track_id
    FOREIGN KEY (track_id)
    REFERENCES track (id);

ALTER TABLE track_meta ADD CONSTRAINT track_meta_fk_meta_id
    FOREIGN KEY (meta_id)
    REFERENCES meta (id);

ALTER TABLE track_meta_source ADD CONSTRAINT track_meta_source_fk_track_meta_id
    FOREIGN KEY (track_meta_id)
    REFERENCES track_meta (id);

ALTER TABLE track_meta_source ADD CONSTRAINT track_meta_source_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_meta_source ADD CONSTRAINT track_meta_source_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);



ALTER TABLE submission ADD CONSTRAINT submission_fk_source_id
    FOREIGN KEY (source_id)
    REFERENCES source (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_format_id
    FOREIGN KEY (format_id)
    REFERENCES format (id);

ALTER TABLE stats_top_accounts ADD CONSTRAINT stats_top_accounts_fk_account_id
    FOREIGN KEY (account_id)
    REFERENCES account (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_meta_id
    FOREIGN KEY (meta_id) REFERENCES meta (id);

ALTER TABLE submission ADD CONSTRAINT submission_fk_foreignid_id
    FOREIGN KEY (foreignid_id)
    REFERENCES foreignid (id);

ALTER TABLE track_mbid_change ADD CONSTRAINT track_mbid_change_fk_track_mbid_id FOREIGN KEY (track_mbid_id) REFERENCES track_mbid (id);
ALTER TABLE track_mbid_change ADD CONSTRAINT track_mbid_change_fk_account_id FOREIGN KEY (account_id) REFERENCES account (id);

ALTER TABLE track_mbid_flag ADD CONSTRAINT track_mbid_flag_fk_track_mbid_id FOREIGN KEY (track_mbid_id) REFERENCES track_mbid (id);
ALTER TABLE track_mbid_flag ADD CONSTRAINT track_mbid_flag_fk_account_id FOREIGN KEY (account_id) REFERENCES account (id);
