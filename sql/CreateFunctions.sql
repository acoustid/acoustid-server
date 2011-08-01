CREATE OR REPLACE FUNCTION generate_api_key() RETURNS varchar
AS $$
    SELECT substring(regexp_replace(encode(decode(md5(current_timestamp::text || to_hex(ceil(random() * 16777215)::int)),'hex'),'base64'), '[/+=]', '', 'g') from 0 for 9);
$$ LANGUAGE 'SQL' IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION extract_fp_query(int[]) RETURNS int[]
AS $$
    SELECT uniq(sort(subarray($1 - 627964279,
		greatest(0, least(icount($1 - 627964279) - 120, 80)), 120)));
$$ LANGUAGE 'SQL' IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION update_account_stats() RETURNS void
AS $$
DECLARE
    last_time timestamp with time zone;
    curr_time timestamp with time zone;
    rec record;
BEGIN
    SELECT last_updated INTO last_time FROM account_stats_control;
    SELECT max(created) INTO curr_time FROM submission;
    FOR rec IN SELECT so.account_id, count(*) AS count FROM submission su
        JOIN source so ON su.source_id = so.id
        WHERE last_time < su.created AND su.created <= curr_time
        GROUP BY so.account_id
    LOOP
        UPDATE account SET submission_count = submission_count + rec.count
        WHERE id = rec.account_id;
    END LOOP;
    UPDATE account_stats_control SET last_updated = curr_time;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fp_hash(int[]) RETURNS bytea
AS $$
    SELECT digest($1::text, 'sha1');
$$ LANGUAGE 'SQL' IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION tr_ins_fingerprint() RETURNS trigger
AS $$
BEGIN
	NEW.hash_full = fp_hash(NEW.fingerprint);
	NEW.hash_query = fp_hash(acoustid_extract_query(NEW.fingerprint));
	RETURN NEW;
END;
$$ LANGUAGE plpgsql;

