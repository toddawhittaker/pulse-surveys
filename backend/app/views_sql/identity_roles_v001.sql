-- The database roles E0-10 establishes — ADR 0001, ADR 0009, ADR 0040, ADR 0043.
--
-- Three are created here, and they are not three of a kind. **Two are connection
-- roles**: pulse_app serves student, instructor, leadership and admin requests,
-- and pulse_care serves the Care queue and nothing else. **One is a definer**:
-- pulse_reveal_definer never connects to anything and exists only to own the
-- SECURITY DEFINER reveal function, so that the one deliberate hole in the wall
-- runs with three grants rather than with the privileges of whoever ran the
-- migration (ADR 0043). The role ADR 0001 names third, pulse_migrate, is still
-- not created: ADR 0040 settles that it is the bootstrap identity of ADR 0009
-- under another name, because the identity a migration runs as cannot itself be
-- created by a migration.
--
-- This file is idempotent in both halves, and the second half is the one that
-- matters. `.env.example` defaults DB_APP_USER=pulse_app, so on any volume the
-- Compose stack initialised, scripts/db-init has already created that role and a
-- bare CREATE ROLE would abort the migration with `role "pulse_app" already
-- exists`. Creating it only when absent would fix that and leave a second
-- problem: whatever the other mechanism made, this migration would trust. So the
-- CREATE is guarded and every ALTER below runs unconditionally, and the migration
-- ends with the attributes stated rather than merely creating them once.
--
-- **LOGIN and the password are deliberately not set here**, and their absence is
-- the ADR 0009 split rather than an omission. This file decides what a role may
-- *do*; whether it can authenticate, and with what credential, belongs to
-- whichever mechanism provisions the deployment — scripts/db-init on the Compose
-- stack, the operator on a managed Postgres. A migration cannot hold a password
-- without holding it in the repository. A role created here is therefore NOLOGIN
-- until a deployment gives it a credential, and a role that already had one keeps
-- it, because no statement below mentions LOGIN.
--
-- The five attributes cleared below are the five `pg_roles` columns that let a
-- role out from under a grant. rolsuper is the obvious one; rolbypassrls alone
-- would read straight through a deny-all row-level policy while `\du` shows
-- nothing unusual, which is what E0-02's security review measured on the real
-- stack. ADR 0001's first consequence — "runtime roles must not own tables and
-- must not be superuser" — is what these statements state.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_app') THEN
        CREATE ROLE pulse_app;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_care') THEN
        CREATE ROLE pulse_care;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_reveal_definer') THEN
        CREATE ROLE pulse_reveal_definer;
    END IF;
END
$$;

ALTER ROLE pulse_app
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

ALTER ROLE pulse_care
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

-- The definer, and NOLOGIN is the whole of what makes it different from the two
-- above. It is guarded and altered exactly like them so that a cluster where
-- somebody has given it CREATEROLE, or LOGIN, is corrected by the next migration
-- rather than trusted — but no mechanism anywhere in this repository gives it a
-- password, because nothing is ever supposed to connect as it. If a deployment
-- finds itself needing one, that is a question for ADR 0043 rather than a line
-- in an init script.
ALTER ROLE pulse_reveal_definer
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOLOGIN INHERIT;

-- CONNECT on this database, whatever it is called, and **for the two connection
-- roles only**. pulse_reveal_definer is deliberately absent from this statement:
-- it is NOLOGIN, so CONNECT would grant it nothing it could use, and leaving it
-- out is the second place this file says out loud that the role is not something
-- to connect as.
--
-- The database name cannot be a bind parameter and cannot be hard-coded —
-- DB_NAME is deployment configuration — so it is quoted as an identifier by
-- `format`. PUBLIC holds CONNECT by default, so on a stock cluster this changes
-- nothing; it is what makes the two roles work on a hardened one where that
-- default has been revoked.
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO pulse_app, pulse_care', current_database()
    );
END
$$;
