DROP INDEX fingerprint_idx_fingerprint;
DROP INDEX fingerprint_idx_fingerprint_short;

DROP FUNCTION process_fp_query(int[]);
DROP FUNCTION extract_short_fp_query(int[]);

CREATE OR REPLACE FUNCTION extract_fp_query(int[]) RETURNS int[]
AS $$
    SELECT uniq(sort(subarray($1 - 627964279,
               greatest(0, least(icount($1 - 627964279) - 120, 80)), 80)));
$$ LANGUAGE 'SQL' IMMUTABLE STRICT;

CREATE INDEX fingerprint_idx_fingerprint ON fingerprint
    USING gin (extract_fp_query(fingerprint) gin__int_ops);

ALTER TABLE fingerprint ADD COLUMN submission_id int;
ALTER TABLE fingerprint ADD COLUMN hash_full bytea;
ALTER TABLE fingerprint ADD COLUMN hash_query bytea;
ALTER TABLE track_mbid ADD COLUMN submission_id int;

CREATE INDEX fingerprint_idx_hash_query ON fingerprint (hash_query);
CREATE INDEX fingerprint_idx_hash_full ON fingerprint (hash_full);

CREATE OR REPLACE FUNCTION fp_hash(int[]) RETURNS bytea
AS $$
    SELECT digest($1::text, 'sha1');
$$ LANGUAGE 'SQL' IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION tr_ins_fingerprint() RETURNS trigger
AS $$
BEGIN
	NEW.hash_full = fp_hash(NEW.fingerprint);
	NEW.hash_query = fp_hash(extract_fp_query(NEW.fingerprint));
	RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_ins_fingerprint BEFORE INSERT ON fingerprint
    FOR EACH ROW EXECUTE PROCEDURE tr_ins_fingerprint();

ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);

ALTER TABLE track_mbid ADD CONSTRAINT track_mbid_fk_submission_id
    FOREIGN KEY (submission_id)
    REFERENCES submission (id);
