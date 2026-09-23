-- What the application may read of the benchmark cohort views — ticket E5-03,
-- SPEC §5.1, §4.1 items 1 and 7, ADR 0001, ADR 0041, and the ruling on
-- docs/disputes/E5-03-01.md: "Grants: SELECT on the four views; EXECUTE on the
-- two functions."
--
-- Four views and one verb. Without this file every read of them is refused with
-- 42501, because the report runs on the connection pulse_app holds and nothing
-- grants that role a privilege in advance.
--
-- **The EXECUTE half is not here**, and that is deliberate rather than an
-- omission: each set function's own file carries its REVOKE from PUBLIC and its
-- GRANT EXECUTE, the way every definer in this tree does, so a reviewer reading
-- one body reads the grant beside it.
--
-- **The withheld verbs are the load-bearing half.** These are aggregates over
-- what students submitted across the institution, so a runtime role that could
-- write to one could rewrite what every instructor is benchmarked against.
-- Postgres would refuse such a write a second time — a view with a GROUP BY is
-- not auto-updatable and the rewriter answers 55000 — but that refusal is
-- identical against a role holding ALL PRIVILEGES, so the ACL is the layer this
-- ticket owns and the tests read the ACL rather than a refused statement
-- (docs/disputes/E4-03-01.md).
--
-- **pulse_care is granted nothing.** The Care surface reaches a threat comment
-- and the audited reveal (SPEC §6.2, ADR 0001); a cohort benchmark is no part
-- of it, and a role gets no privilege it has no use for.
--
-- **USAGE ON SCHEMA public is not granted again here.** identity_grants_v001.sql
-- grants it to pulse_app and identity_grants_v002.sql restates it; an ACL entry
-- records no history, so a third grant would be indistinguishable from those
-- and any matching revoke would remove all of them.
--
-- **The downgrade has nothing to revoke.** These four privileges are recorded
-- on objects the same revision creates, and dropping a view takes its ACL
-- entries with it. The column grants this ticket's definer role holds are the
-- opposite case — they sit on base tables that outlive the revision — so the
-- revision revokes those by hand.
--
-- **This widens what pulse_app can reach, and it is meant to be visible.**
-- SANCTIONED_VIEW_COLUMNS in tests/integration/test_identity_grants.py is the
-- hand-written record every readable view column is compared against as an
-- equality in both directions, deliberately not derived from these files so
-- that a widening cannot justify itself. The four entries admitting these views
-- carry the sentence that admits them: not one of their columns names a person.

GRANT SELECT ON public.benchmark_cohort_rating_week TO pulse_app;
GRANT SELECT ON public.benchmark_cohort_week TO pulse_app;
GRANT SELECT ON public.benchmark_cohort_rating_term_axis TO pulse_app;
GRANT SELECT ON public.benchmark_cohort_term_axis TO pulse_app;
