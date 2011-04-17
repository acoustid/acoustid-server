MODULE_big = acoustid
OBJS = acoustid_compare.o
DATA_built = acoustid.sql
DATA = uninstall_acoustid.sql
REGRESS = acoustid

PG_CONFIG = pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
