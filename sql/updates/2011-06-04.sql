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

