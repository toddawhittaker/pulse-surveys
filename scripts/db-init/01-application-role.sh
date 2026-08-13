#!/usr/bin/env bash
# Provision the role the application connects as — ticket E0-02.
#
# The Postgres image creates exactly one role, from POSTGRES_USER, and `initdb`
# makes it the cluster superuser. That is unavoidable. What is avoidable is
# pointing DATABASE_URL at it: a superuser bypasses grants and row-level
# security entirely, and can run `COPY … FROM PROGRAM`, which is a shell in the
# database container reachable from any SQL injection in the application.
#
# docs/adr/0001-identity-separation-by-database-role.md says so directly —
# "Runtime roles must not own tables and must not be superuser. Both bypass
# grants entirely, which would make the whole scheme decorative." E0-10 builds
# the three-role scheme that ADR describes. This script does the one part that
# cannot wait for it, because E0-04 opens the first connection and every ticket
# between the two would have a superuser on the other end of it.
#
# Everything in `/docker-entrypoint-initdb.d` runs once, against an empty data
# directory, before the server accepts a TCP connection. An existing
# `postgres-data` volume never sees this file; `docker compose down -v` is what
# discards one.
#
# The grant is deliberately only CONNECT. This role cannot create a table, so
# `alembic upgrade head` cannot run as it — which is a question E0-04 has to
# answer rather than a gap here, and E0-04's ticket carries it.

set -euo pipefail

: "${POSTGRES_USER:?}" "${POSTGRES_DB:?}" "${DB_APP_USER:?}" "${DB_APP_PASSWORD:?}"

if [ "${DB_APP_USER}" = "${POSTGRES_USER}" ]; then
    echo "FAIL: DB_APP_USER and DB_SUPERUSER name the same role (${DB_APP_USER})." >&2
    echo "      The application would connect as the superuser, which is the" >&2
    echo "      thing this script exists to prevent. Set them to different names." >&2
    exit 1
fi

# Values reach SQL through psql's own interpolation rather than through the
# shell: `:"name"` becomes a quoted identifier and `:'value'` a quoted literal,
# both escaped by psql. The heredoc is quoted so the shell expands nothing.
psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" --no-password \
     --set ON_ERROR_STOP=1 \
     --set app_user="${DB_APP_USER}" \
     --set app_password="${DB_APP_PASSWORD}" \
     --set db_name="${POSTGRES_DB}" <<'SQL'
CREATE ROLE :"app_user"
    LOGIN
    PASSWORD :'app_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
SQL

echo "Created application role '${DB_APP_USER}' (NOSUPERUSER, CONNECT only)."
