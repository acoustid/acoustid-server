\set ON_ERROR_STOP 1
BEGIN;

CREATE TRIGGER tr_ins_fingerprint BEFORE INSERT ON fingerprint
    FOR EACH ROW EXECUTE PROCEDURE tr_ins_fingerprint();

COMMIT;
