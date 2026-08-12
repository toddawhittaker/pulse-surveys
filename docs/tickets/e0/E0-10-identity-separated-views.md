# E0-10 — Identity-separated read views

**ID:** E0-10
**Branch:** `e0/identity-separated-views`
**Depends on:** E0-08, E0-09

## Context

Instructor and leadership read paths go through views that *structurally cannot*
join to identity columns — enforced in the database, not in application code, so
the guarantee survives a future careless query (§8, `CLAUDE.md`). This ticket
establishes that mechanism and lands the first §4.1 invariant assertions in CI.
It is the ticket that turns confidentiality from a convention into a property.

Read first: SPEC §4 and §4.1, §8 (identity separation), §9.1 (the invariant
suite), §13 (`views_sql/` ships as migrations, not ORM convention).

## Scope

- `backend/app/views_sql/` with the first identity-separated views shipped as
  Alembic migrations: a section-roster view and an enrollment-count view that
  expose section membership and counts with **no** identity columns reachable.
- A dedicated database role or grant model such that the instructor and
  leadership read path physically lacks `SELECT` on identity columns. If a
  grant-based approach proves impractical on the deployment target, document why
  and fall back to views that omit the columns, stating the weaker guarantee
  plainly.
- Query helpers alongside the views so callers get a typed way in that does not
  tempt them to hand-write a join.
- The first `@pytest.mark.invariant` tests, asserting §4.1 items reachable this
  early: no student-visible path exposes another section, and no instructor read
  path can reach an identity column.
- A structural test that enumerates identity columns via E0-08's marker
  convention and asserts none appears in any view in `views_sql/` — so a view
  added later that leaks identity fails CI without anyone remembering to check.
- Remove `--allow-empty` from the invariant checker in `.github/workflows/ci.yml`
  and in `make invariants`. From this ticket on, a skipped invariant is a build
  failure.

## Out of scope

- Views over responses, comments, and summaries — those arrive with the tables,
  in E2 and E4.
- Small-N suppression logic (E4) and benchmark min-N (E5); this ticket carries
  no thresholds.
- Care-role re-identification and its audit log (E10).

## Acceptance criteria

- [ ] Views ship as Alembic migrations under `views_sql/`, not as ORM
      constructs; `alembic upgrade head` creates them and `alembic check` is
      clean.
- [ ] A query through the instructor read path that attempts to select an
      identity column fails — at the database level, with the error surfaced in
      a test.
- [ ] The structural test enumerates identity columns and finds none in any
      view. Adding an identity column to a view makes it fail; verify by hand,
      then revert.
- [ ] At least two `invariant`-marked tests exist and run.
- [ ] CI fails if an invariant test is skipped or xfailed — verify by
      temporarily marking one `skip` and watching the pipeline go red, then
      revert.
- [ ] The invariant checker's `--allow-empty` flag is gone from both CI and the
      Makefile.

## Definition of done

**Tests apply, and this ticket owns the strictest ones in E0.** Invariant tests
per §9.1, plus the structural enumeration test. Integration tests — they need a
real Postgres to exercise grants and views.

**Docs apply.** `CONTRIBUTING.md` gains a short note that read paths go through
`views_sql/` and that adding a view means adding an invariant test.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies and is the most important in E0 so far.** This is a
⚠-grade concern by §14.2's standard even though E0 is not a ⚠ epic: review the
grant model for a bypass, confirm the views cannot be joined back to identity
through a shared key, and check that no helper leaks a raw session that sidesteps
them. Ask for line-by-line human review of the migration SQL.
