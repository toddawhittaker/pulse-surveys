#!/usr/bin/env bash
# Provision the role the application connects as — ticket E0-02.
#
# The Postgres image creates exactly one role, from POSTGRES_USER, and `initdb`
# makes it the cluster superuser. docs/adr/0009 sanctions that role and says
# what it is for: migrations and system-level tasks, and nothing else. This
# script adds the second role — the one the application connects as day to day,
# which must not be a superuser, because a superuser bypasses grants and
# row-level security entirely and can run `COPY … FROM PROGRAM`, a shell in the
# database container reachable from any SQL injection in the application.
#
# docs/adr/0001-identity-separation-by-database-role.md line 71 still governs
# that half — "Runtime roles must not own tables and must not be superuser" —
# and is untouched by ADR 0009. E0-10 builds the full three-role scheme on top
# of this one; ADR 0009 records which mechanism provisions what, so the two do
# not collide.
#
# Everything in `/docker-entrypoint-initdb.d` runs once, against an empty data
# directory, before the server accepts a TCP connection. An existing
# `postgres-data` volume never sees this file; `docker compose down -v` is what
# discards one. It runs only where that hook exists, which is the Compose stack
# — a managed Postgres, CI's `services.postgres`, and E0-04's testcontainers
# fixture each provision the role their own way. ADR 0009 has the table.
#
# The only grant made here is CONNECT. That is not the same as "no privileges":
# the role keeps Postgres's PUBLIC defaults, so it can also connect to the other
# databases in the cluster and create temporary tables. What it cannot do is
# create a table in this one, which is why migrations run as the superuser
# identity (ADR 0009) rather than as this role.

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

echo "Created application role '${DB_APP_USER}' (NOSUPERUSER; granted CONNECT)."
