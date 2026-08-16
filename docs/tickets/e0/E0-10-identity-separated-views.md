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
suite), §13 (`views_sql/` ships as migrations, not ORM convention), and
[ADR 0009](../../adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md),
which changes who provisions two of the three roles below.

Also **"What the built tickets settled" in [the epic README](README.md)**. Two
items reach this ticket. `tests/conftest.py` already provides an
`application_engine` fixture connected as the non-superuser application role,
which is the connection most of this ticket's invariants need to be asserted
over — E0-04 built it so that tests cannot pass under privileges production
lacks, which is precisely the failure mode §4.1 exists to prevent. And
`test_application_role_privileges.py` already asserts that role is not a
superuser and cannot create a table; this ticket's "neither runtime role owns any
table, and neither is a superuser" criterion extends that guard rather than
starting it.

## Reconcile first: `pulse_app` already exists

E0-02 provisions an application role before this ticket runs.
`scripts/db-init/01-application-role.sh` creates it at `initdb`, and
`.env.example` defaults `DB_APP_USER=pulse_app` — **the same name this ticket's
migration creates**. On any database initialised by the Compose stack since
E0-02, a plain `CREATE ROLE pulse_app` aborts the migration with:

```
ERROR:  role "pulse_app" already exists
```

Two things to settle, and neither is optional:

1. **This ticket's role migration must be idempotent.** It has to tolerate a
   role that already exists, and still end with the attributes and grants this
   ticket requires — so `CREATE ROLE` guarded by a `pg_roles` lookup, followed
   by the `ALTER ROLE` and `GRANT`/`REVOKE` statements applied unconditionally.
   Creating it only when absent and assuming a bootstrap-created role is already
   correct would leave the two mechanisms free to disagree.
2. **`pulse_migrate` needs reconciling with ADR 0009.** The scope below gives
   it schema ownership and the Alembic connection, but ADR 0009 decides that
   migrations run as the bootstrap superuser identity (`DB_SUPERUSER`), which is
   what E0-04 wires up. Either `pulse_migrate` *is* that identity under a
   different name in `.env`, or this ticket is reintroducing a separate
   non-superuser owner and ADR 0009 has to be amended in the same pull request
   rather than contradicted quietly.

**Provisioning is not uniform across environments**, and this ticket is where
that stops being tolerable, because the invariant suite asserts properties of
these roles. ADR 0009 carries the table: the Compose stack gets `pulse_app` from
the `initdb` hook; `migration-drift`'s `services.postgres`, E0-04's
testcontainers fixture, and any managed Postgres do not run that hook at all. If
this ticket's migration is idempotent as above, it becomes the single mechanism
that works everywhere and the bootstrap script becomes a convenience — which is
the cleanest resolution, and worth stating in the pull request either way.

## Scope

- `backend/app/views_sql/` with the first identity-separated views shipped as
  Alembic migrations: a section-roster view and an enrollment-count view that
  expose section membership and counts with **no** identity columns reachable.
- **Three database roles**, established as migrations — idempotently, and
  reconciled with ADR 0009 as set out above:
  - `pulse_migrate` owns the schema and runs Alembic. Not used at runtime. See
    point 2 above before building this one.
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
- **Close the two holes in that marker convention first — this ticket is where
  they stop being theoretical.** E0-08's independent security review found both,
  and neither was blocking there precisely because no grants existed yet. This
  ticket lands the grants. Details in the "Fix the marker before you build on
  it" section below.
- Remove `--allow-empty` from the invariant checker in `.github/workflows/ci.yml`
  and in `make invariants`. From this ticket on, a skipped invariant is a build
  failure.

## Fix the marker before you build on it

The whole of this ticket rests on being able to enumerate identity-bearing
columns programmatically. E0-08 built that convention (ADR 0022, `identity_` name
prefix) and its security review found two ways it fails quietly. Both are
recorded here rather than in E0-08 because E0-08 has no read paths and no grants
— nothing there is exposed by either. **This ticket adds the grants, so this is
the ticket where an unmarked identity column becomes an instructor-visible one.**

**1. Discovery is by the name fragments `("name", "email")`.** A roster sync
storing an NRPS or LTI claim as `picture`, `login_id`, `lis_person_sourcedid`,
`phone`, `sortable`, or `given`/`family` spelled without "name" lands an
identity column that the sweep passes unmarked and unnoticed. The convention
requires a human to name a column in a way the sweep happens to recognise, which
is the property a tripwire is supposed to remove.

**2. The table sweep is one foreign-key hop, not a fixed point.**
`people_tables` in `tests/integration/test_identity_column_marker.py` tests each
table's foreign keys against the three-table constant rather than against the set
it is building, so a table linking to a table that links to `user` is never
swept. `response` is covered today; `answer` and `threat_case` are not — and
`threat_case` is §6.2's Care queue, the most identity-adjacent table in the
system. This one is a four-line fix and should not wait.

Neither is exploitable as of E0-08: no such column exists and no grants exist.
Both are load-bearing from this ticket onward.

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

- [ ] **The marker sweep reaches every table that can hold identity**, by
      iterating the foreign-key walk to a fixed point rather than one hop. A test
      asserts `threat_case` and `answer` are in the swept set, since both are
      reachable only at two hops and `threat_case` is the Care queue.
- [ ] **An identity column whose name contains neither "name" nor "email" is
      still caught.** Decide how — a declared list on the model, a type, a
      `Column.info` flag carried into the database, or a widened fragment set —
      and say in the pull request what the new convention cannot see, because
      every version of this has a blind spot and the one that goes unstated is
      the one that bites. Add a test that fails when a plausibly-named identity
      column (`login_id`, `picture`, `lis_person_sourcedid`) is added unmarked.
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
