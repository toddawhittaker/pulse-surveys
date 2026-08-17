#!/usr/bin/env bash
# Provision the role the Care queue connects as — ticket E0-10.
#
# The third of the three roles ADR 0001 names, and the counterpart to
# `01-application-role.sh` beside it: same mechanism, same reasoning, opposite
# job. `pulse_app` serves every ordinary request and can never reach a student's
# name; `pulse_care` serves SPEC §6.2's Care queue and is the only role in the
# cluster that can, through one SECURITY DEFINER function that writes an audit
# row in the same transaction as the read.
#
# **This script grants nothing.** It creates a role that can log in, and that is
# all. Every privilege either runtime role holds is written by the E0-10
# migration (`backend/app/views_sql/identity_grants_v001.sql`), which is the one
# mechanism that runs in every environment — the Compose stack, CI's drift job,
# the testcontainers fixture and a managed Postgres provision roles four
# different ways, and only one of them runs this file. The split is the reverse
# of `01-application-role.sh`'s CONNECT grant, and deliberately: a migration
# cannot hold a password without holding it in the repository, and a shell script
# that hands out grants is a second place the grant model lives.
#
# Everything in `/docker-entrypoint-initdb.d` runs once, against an empty data
# directory, before the server accepts a TCP connection. An existing
# `postgres-data` volume never sees this file, so a stack that was up before
# E0-10 needs `docker compose down -v` before the Care connection can
# authenticate. Until then the role exists — the migration creates it — with no
# way to log in, which fails as an authentication error rather than as a silent
# grant of access to the wrong connection.
#
# The `01-` script's second caller, CI's `migration-drift` job, does not run this
# one and does not need to: that job runs migrations and never opens a Care
# connection.

set -euo pipefail

: "${POSTGRES_USER:?}" "${POSTGRES_DB:?}" "${DB_CARE_USER:?}" "${DB_CARE_PASSWORD:?}"

if [ "${DB_CARE_USER}" = "${POSTGRES_USER}" ]; then
    echo "FAIL: DB_CARE_USER and DB_SUPERUSER name the same role (${DB_CARE_USER})." >&2
    echo "      The Care queue would connect as the superuser, which bypasses every" >&2
    echo "      grant this ticket is made of. Set them to different names." >&2
    exit 1
fi

if [ "${DB_CARE_USER}" = "${DB_APP_USER:-}" ]; then
    echo "FAIL: DB_CARE_USER and DB_APP_USER name the same role (${DB_CARE_USER})." >&2
    echo "      Then every instructor and leadership request runs on the one" >&2
    echo "      connection that can execute the audited reveal, and SPEC 4.1's" >&2
    echo "      separation is a convention again. Set them to different names." >&2
    exit 1
fi

# The role and nothing else. Identifiers reach SQL through psql's own
# interpolation rather than through the shell: `:"name"` becomes a quoted
# identifier, escaped by psql. The heredoc is quoted so the shell expands
# nothing. This statement carries no secret, which matters because Postgres logs
# the full text of a failed statement and "role already exists" is the ordinary
# result of re-running after a partial failure.
psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" --no-password \
     --set ON_ERROR_STOP=1 \
     --set care_user="${DB_CARE_USER}" <<'SQL'
CREATE ROLE :"care_user"
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;
SQL

# The password, set separately and never sent in the clear — the reasoning is in
# `01-application-role.sh` at length and is not repeated here. `PASSWORD
# :'literal'` would have psql expand the plaintext into the statement before
# sending it, so the server would receive, and on any error log, the password
# itself; that was reproduced against this stack. `\password` hashes client-side
# and sends only a SCRAM-SHA-256 verifier.
printf '%s\n%s\n' "${DB_CARE_PASSWORD}" "${DB_CARE_PASSWORD}" |
    psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" --no-password \
         --set ON_ERROR_STOP=1 \
         --set care_user="${DB_CARE_USER}" \
         --command '\password :"care_user"' > /dev/null

echo "Created Care role '${DB_CARE_USER}' (NOSUPERUSER; the E0-10 migration grants it)."
