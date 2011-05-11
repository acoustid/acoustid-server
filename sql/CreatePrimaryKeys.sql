ALTER TABLE account ADD CONSTRAINT account_pkey PRIMARY KEY (id);
ALTER TABLE account_openid ADD CONSTRAINT account_openid_pkey PRIMARY KEY (openid);
ALTER TABLE application ADD CONSTRAINT application_pkey PRIMARY KEY (id);
ALTER TABLE source ADD CONSTRAINT source_pkey PRIMARY KEY (id);
ALTER TABLE format ADD CONSTRAINT format_pkey PRIMARY KEY (id);
ALTER TABLE fingerprint ADD CONSTRAINT fingerprint_pkey PRIMARY KEY (id);
ALTER TABLE track ADD CONSTRAINT track_pkey PRIMARY KEY (id);
ALTER TABLE track_mbid ADD CONSTRAINT track_mbid_pkey PRIMARY KEY (track_id, mbid);
ALTER TABLE submission ADD CONSTRAINT submission_pkey PRIMARY KEY (id);
ALTER TABLE stats ADD CONSTRAINT stats_pkey PRIMARY KEY (id);
ALTER TABLE stats_top_accounts ADD CONSTRAINT stats_top_accounts_pkey PRIMARY KEY (id);

