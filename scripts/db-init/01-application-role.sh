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
# discards one.
#
# **This script has a second caller.** CI's `migration-drift` job runs it as an
# ordinary step against its `services.postgres` container, which has no init
# hook, so the drift gate checks the schema against the role shape a deployment
# has rather than against a bare superuser cluster (ADR 0009's provisioning
# table, settled by ADR 0012). That caller reaches the server over TCP and
# supplies PGHOST, PGPORT and PGPASSWORD; everything else it passes is what the
# Compose `db` service passes. Nothing here may assume a local socket or a
# trusted connection. A managed Postgres and E0-04's testcontainers fixture
# still provision the role their own way.
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

# The role and its grant, with no password anywhere in the statement text.
#
# Identifiers reach SQL through psql's own interpolation rather than through the
# shell: `:"name"` becomes a quoted identifier, escaped by psql. The heredoc is
# quoted so the shell expands nothing.
#
# This is the statement that can fail — "role already exists" is the ordinary
# result of re-running after a partial failure, and `pulse_app` is the name
# E0-10's migration also creates. Postgres logs the full statement text of a
# failed statement (`log_min_error_statement` defaults to `error`), so what this
# one carries matters. It carries no secret.
psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" --no-password \
     --set ON_ERROR_STOP=1 \
     --set app_user="${DB_APP_USER}" \
     --set db_name="${POSTGRES_DB}" <<'SQL'
CREATE ROLE :"app_user"
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
SQL

# The password, set separately and never sent in the clear.
#
# `PASSWORD :'literal'` would have psql expand the plaintext into the statement
# *before* sending it, so the server receives — and on any error logs —
# `... PASSWORD '<plaintext>'`. That was reproduced: a canary appeared verbatim
# in `docker compose logs db`. A container log has a far wider audience than
# `.env`; CI dumps it on failure and a managed Postgres ships it to a log
# aggregator.
#
# `\password` instead. It hashes client-side and sends only a SCRAM-SHA-256
# verifier, so the plaintext never reaches the server, its log, or its
# statement history. The verifier is a salted 4096-iteration digest and is not
# replayable — completing SCRAM from it needs a preimage of the stored key — so
# even the worst case here is an offline attack rather than a usable credential.
#
# The password arrives on stdin, via a shell builtin, so it is in no argv and no
# environment. `\password` prompts twice, hence the two lines. It reads them
# from stdin because the container has no controlling terminal; a failure still
# exits non-zero, which was checked rather than assumed. stdout is dropped
# because the two prompts are addressed to a human who is not there; errors go
# to stderr and are kept.
printf '%s\n%s\n' "${DB_APP_PASSWORD}" "${DB_APP_PASSWORD}" |
    psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" --no-password \
         --set ON_ERROR_STOP=1 \
         --set app_user="${DB_APP_USER}" \
         --command '\password :"app_user"' > /dev/null

echo "Created application role '${DB_APP_USER}' (NOSUPERUSER; granted CONNECT)."
