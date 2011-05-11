CREATE TABLE stats_top_accounts (
    id serial NOT NULL,
	account_id int NOT NULL,
	count int NOT NULL
);

ALTER TABLE stats_top_accounts ADD CONSTRAINT stats_top_accounts_pkey PRIMARY KEY (id);

ALTER TABLE stats_top_accounts ADD CONSTRAINT stats_top_accounts_fk_account_id
    FOREIGN KEY (account_id)
    REFERENCES account (id);

