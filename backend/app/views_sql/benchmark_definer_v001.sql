-- The owner of the two benchmark set functions, and everything it may read —
-- ticket E5-03, SPEC §4.1 items 1 and 7, §5.1, §8, ADR 0043, ADR 0165, and the
-- ruling on docs/disputes/E5-03-01.md.
--
-- `pulse_benchmark_definer` is a NOLOGIN role that exists for nothing but
-- owning benchmark_set_week and benchmark_set_rating_week, so that "the
-- definer's privileges" is a list a reviewer can read in this file against
-- those two bodies (ADR 0043's pattern). Nothing connects as it and no
-- mechanism in this repository gives it a password.
--
-- **A new role rather than a reuse of pulse_resolve_definer, and the reason is
-- blast radius rather than names.** That role cannot read a name either: it
-- holds `user`(id, lti_platform_id, lms_user_id), `person`(id, user_id) and
-- `web_login_subject` (identity_resolution_v001.sql,
-- web_identity_resolution_v001.sql), which are cross-platform identifier
-- columns. What it is *for* is resolving one identifier to another, and a body
-- whose whole job is counting has no use for that reach. Keeping the two owners
-- disjoint is what makes "the definer's privileges" readable against the bodies
-- that spend them, and it runs both ways: a later widening of either owner then
-- widens one function family rather than two. What this one may read is listed
-- below in full, at column grain, and there is not a name or an address among
-- them.
--
-- **Why an owner with these reads exists at all**, said accurately rather than
-- as a wall it is not. pulse_app can already read `response` and `answer`
-- table-wide (the E2 submission path), so nothing here is keeping the
-- application away from rows it is otherwise refused. This owner exists so that
-- the counting happens inside bodies that answer in aggregates: the alternative
-- the work order asked for was a person-keyed **view** on the sanctioned read
-- surface, which E5-03's scope forbids in five words — "section id and numbers,
-- never a person" — and which the ruling on docs/disputes/E5-03-01.md withdrew.
-- ADR 0165 carries the argument, and that file's amendment records the claim
-- this paragraph no longer makes.
--
-- **Column grain, and the columns are the ones the two bodies name.** A
-- table-wide SELECT would hand this owner every column those tables ever grow,
-- which is the widening a reviewer would have no way to notice. `response` is
-- the sensitive one: the author key is granted because the distinct count of
-- people is computed over it, and it is the only column here that reaches a
-- person at all — it is grouped away and never returned.
--
-- The role is created only when absent and its attributes are stated
-- unconditionally, which is identity_roles_v001.sql's rule and its reason: what
-- some other mechanism made, this file corrects rather than trusts. CONNECT is
-- deliberately not granted; it is NOLOGIN and nothing is supposed to connect as
-- it.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_benchmark_definer'
    ) THEN
        CREATE ROLE pulse_benchmark_definer;
    END IF;
END
$do$;

ALTER ROLE pulse_benchmark_definer
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOLOGIN INHERIT;

GRANT SELECT (id, user_id, section_id, week_id) ON public.response
    TO pulse_benchmark_definer;
GRANT SELECT (response_id, question_id, rating, workload_hours) ON public.answer
    TO pulse_benchmark_definer;
GRANT SELECT (id, kind, stream) ON public.question TO pulse_benchmark_definer;
GRANT SELECT (id, term_id, start_date) ON public.section TO pulse_benchmark_definer;
GRANT SELECT (id, start_date) ON public.term TO pulse_benchmark_definer;
GRANT SELECT (id, number) ON public.week TO pulse_benchmark_definer;
