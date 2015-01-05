CREATE TABLE stats_user_agents (
    id serial NOT NULL,
    date date NOT NULL,
    application_id int NOT NULL,
    user_agent varchar NOT NULL,
    ip varchar NOT NULL,
    count int NOT NULL default 0
);

ALTER TABLE stats_user_agents ADD CONSTRAINT stats_user_agents_pkey PRIMARY KEY (id);

CREATE INDEX stats_lookups_idx_date ON stats_lookups (date);
CREATE INDEX stats_user_agents_idx_date ON stats_user_agents (date);
