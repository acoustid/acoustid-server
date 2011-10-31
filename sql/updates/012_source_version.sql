ALTER TABLE source ADD version varchar;

DROP INDEX source_idx_uniq;
CREATE UNIQUE INDEX source_idx_uniq ON source (application_id, account_id, version);

