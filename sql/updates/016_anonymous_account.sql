BEGIN;

ALTER TABLE account ADD application_id int;
ALTER TABLE account ADD application_version varchar;
ALTER TABLE account ADD created_from inet;

ALTER TABLE account ADD CONSTRAINT account_fk_application_id
    FOREIGN KEY (application_id)
    REFERENCES application (id);

COMMIT;

