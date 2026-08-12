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
- **Three database roles**, established as migrations:
  - `pulse_migrate` owns the schema and runs Alembic. Not used at runtime.
  - `pulse_app` serves student, instructor, leadership, and admin requests. It
    has **no grant of any kind** on `user_identity` (E0-08). An instructor
    screen cannot leak a name because the connection it runs on cannot read the
    table.
  - `pulse_care` serves the Care queue only. It also gets **no** `SELECT` on
    `user_identity` — see the reveal function below.
- Two runtime connection pools. **The pool is bound to the service, not to the
  person** — only the Care service module can obtain a `pulse_care` session, and
  it independently verifies the actor holds a live `CARE` assignment before
  doing anything. Two conditions, both required, so neither a routing mistake
  nor a stale assignment is enough on its own. Selecting a pool from "the
  actor's role" is not sufficient: a person may hold more than one assignment,
  and that phrasing leaves the answer ambiguous exactly where it matters most.
- A caller can never choose its own pool, and no general-purpose helper hands
  out a `pulse_care` session.
- **The Care path must remain open, and this ticket proves it.** Care
  re-identification is the one legitimate route to identity (§4, §6.2), and it
  is deliberately not blocked. `pulse_care` gets `EXECUTE` on a single
  `SECURITY DEFINER` function that returns identity **and writes the audit row
  in the same transaction**, so a name cannot be obtained without leaving a
  record. E0 ships this as a minimal proof of mechanism — there is no case model
  until E10 — and E10 replaces the stub with the real audited reveal.
- Note for whoever builds this: a table's **owner** and any **superuser** bypass
  grants entirely. If a runtime role owns the tables or is superuser, the whole
  scheme is decorative. Verify the runtime roles are neither.
- If a grant-based approach proves impractical on the deployment target,
  document why and fall back to views that omit the columns, stating the weaker
  guarantee plainly rather than implying the stronger one.
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
- The real Care re-identification flow — the case model, the two-action queue,
  disposition notes, and the full audit schema (E10). This ticket ships only the
  role, the grant, and a proof-of-mechanism function, so that E10 inherits a
  door rather than a wall.
- The conflict-of-interest flag on a reveal (SPEC §6.2, `CLAUDE.md`) is E10's to
  compute. What this ticket owes it is an audit row shape that can carry the
  flag, so E10 adds a value rather than redesigning the table. Leave the column
  or leave room for it, and say which in the pull request.

## Acceptance criteria

- [ ] Views ship as Alembic migrations under `views_sql/`, not as ORM
      constructs; `alembic upgrade head` creates them and `alembic check` is
      clean.
- [ ] A query on the `pulse_app` connection that selects from `user_identity`
      fails at the database level — permission denied, not an empty result. A
      test asserts the failure and its cause.
- [ ] `pulse_app` cannot reach identity by joining either: attempting to join a
      view back to `user_identity` fails for the same reason.
- [ ] **A `pulse_care` connection can still obtain identity** through the
      `SECURITY DEFINER` function. A test asserts this succeeds — the Care path
      is a requirement, not an oversight, and this test is what stops a later
      change from silently closing it.
- [ ] Calling that function writes an audit row in the same transaction. A test
      asserts that rolling back the transaction discards both the read and the
      audit row, so the two cannot come apart.
- [ ] `pulse_care` cannot `SELECT` from `user_identity` directly — only through
      the function.
- [ ] Requesting a `pulse_care` session from outside the Care service module
      fails. A test asserts that a reporting-path caller cannot obtain one even
      when the acting person also holds a `CARE` assignment. **This is the
      two-hat case and it is expected in production** — a Care staffer who also
      teaches — so it is a required test, not a hypothetical one. Their
      instructor requests must run on `pulse_app` with no path to identity.
- [ ] A person with no live `CARE` assignment cannot reach identity through the
      function even if the Care service is somehow reached — the assignment
      check and the pool binding are independent.
- [ ] Neither runtime role owns any table, and neither is a superuser. A test
      asserts both, since either would silently void every grant above.
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
⚠-grade concern by §14.2's standard even though E0 is not a ⚠ epic. Review the
grant model for a bypass, confirm the views cannot be joined back to identity
through a shared key, and check that no helper leaks a raw session that
sidesteps them. Review the `SECURITY DEFINER` function especially closely — it
is deliberately the one hole in the wall, so it needs a fixed `search_path`, no
caller-controlled SQL, and no path that returns identity without writing the
audit row. Ask for line-by-line human review of the migration SQL.
