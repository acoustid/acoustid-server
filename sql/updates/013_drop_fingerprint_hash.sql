DROP TRIGGER tr_ins_fingerprint ON fingerprint;

ALTER TABLE fingerprint DROP COLUMN hash_query;
ALTER TABLE fingerprint DROP COLUMN hash_full;
