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
-- **A new role rather than a reuse of pulse_resolve_definer**, and the reason
-- is the whole of what this owner is for. That role holds column grants on the
-- `user` and `person` tables, so a body whose job is to count students would
-- have had an owner that can read their names. The two owners' grants stay
-- disjoint, and this one reaches no identity column of any kind: what it may
-- read is listed below in full, at column grain, and there is not a name or an
-- address among them.
--
-- **Why an owner with these reads exists at all.** A benchmark over an
-- arbitrary section set has to count *distinct students* across the whole set
-- (SPEC §5.1's comparison sets; docs/MISTAKES.md entry 50 on why the unit has
-- to be people), and any relation wide enough to let the application do that
-- arithmetic for itself is a relation keyed to a student, spanning every
-- section of a cohort in the current and every retained prior term. E5-03's own
-- scope forbids that in five words — "section id and numbers, never a person" —
-- and the ruling on docs/disputes/E5-03-01.md withdrew the view that would have
-- carried it. So the arithmetic happens where the person rows live, under this
-- owner, and only numbers come back. ADR 0150's preference for a plain grant is
-- answered head-on in ADR 0165: a plain grant cannot do this.
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
