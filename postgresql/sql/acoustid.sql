SET client_min_messages = warning;
\set ECHO none
\i acoustid.sql
\set ECHO all
RESET client_min_messages;

SELECT acoustid_compare('{}'::int4[], '{}'::int4[]);
SELECT acoustid_compare('{1}'::int4[], '{}'::int4[]);
SELECT acoustid_compare('{1}'::int4[], '{1}'::int4[]);
SELECT acoustid_compare('{1}'::int4[], '{2}'::int4[]);
SELECT acoustid_compare('{1}'::int4[], '{6}'::int4[]);
SELECT acoustid_compare('{1}'::int4[], '{1,6}'::int4[]);
SELECT acoustid_compare('{1,56}'::int4[], '{1,6}'::int4[]);
SELECT acoustid_compare('{448,56}'::int4[], '{1,6}'::int4[]);

SELECT acoustid_compare('{0,7,56,3584}'::int4[], '{0,7,56,448}'::int4[]);
SELECT acoustid_compare('{7,0,7,56,3584}'::int4[], '{0,7,56,448}'::int4[]);
SELECT acoustid_compare('{0,7,56,3584}'::int4[], '{7,0,7,56,448}'::int4[]);

SELECT acoustid_compare('{65535,65535,1,6,65535,65535}'::int4[], '{1,6}'::int4[]);
SELECT acoustid_compare('{1,6}'::int4[], '{65535,65535,1,6,65535,65535}'::int4[]);

SELECT acoustid_compare('{1,1,1,1,1}'::int4[], '{1,1,1,1,1}'::int4[]);

