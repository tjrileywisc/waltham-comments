#!/bin/bash

# create readonly user, give them select only access to current tables, and any newly created ones

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
    CREATE USER readonly WITH PASSWORD '$POSTGRES_READONLY_PASSWORD';
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
EOSQL