# E0 — Foundations: build order

Thirty-seven tickets decomposing the E0 tickets in SPEC §14.3. Each is sized for a
single focused session and leaves the repository in a working state: CI green,
Compose stack healthy, nothing half-wired at a boundary.

Say **"build E0, ticket 3"** and it means E0-03.

Branch names follow the ticket convention in `CONTRIBUTING.md`: cut
`e0/<slug>` from `epic/e0-foundations`, one ticket per branch, one pull request
into the epic branch.

Already done, do not rebuild — reference these instead: the branch and pull
request model (#1, #2), the secrets policy (#3), and the CI pipeline with
`make ci`, the checker scripts, and Dependabot (#5).

## Build order

| # | Ticket | Depends on | Summary |
|---|---|---|---|
| 01 | [Backend skeleton and configuration surface](E0-01-backend-skeleton.md) | none | FastAPI app factory, env-driven `Settings`, `.env.example`, `/healthz`; turns on the ruff, mypy, audit, and license gates. |
| 02 | [Backend Dockerfile and Compose stack](E0-02-compose-stack.md) | 01 | `api`, `db`, `redis`, `mailpit` with real health checks; `docker compose up` works. |
| 03 | [Celery worker and beat](E0-03-celery-worker-beat.md) | 02 | Celery app, `worker` and `beat` services with health checks that fail when the broker is down. |
| 04 | [Database session and Alembic baseline](E0-04-db-session-alembic.md) | 02 | Engine, session, migration chain, testcontainers fixture; turns on the migration-drift and test gates. |
| 05 | [Org containment schema](E0-05-org-containment-schema.md) | 04 | Institution through section, with course level derived from the course number. |
| 06 | [Term calendar and start-letter map schema](E0-06-term-calendar-schema.md) | 04 | `term`, `week`, `survey_window`, `start_letter_map`; timezone-aware throughout. |
| 07 | [Section-code parser and date derivation](E0-07-section-code-parser.md) | 05, 06 | Parse `R3WW`, derive length, dates, and modality; Hypothesis property tests over the full letter map. |
| 08 | [Identity schema and LTI registration tables](E0-08-identity-schema.md) | 04, 05 | `user` split from `user_identity` so identity is table-level, plus `person`, `enrollment`, and the LTI registration tables. |
| 09 | [Role assignments and the supervision graph](E0-09-role-assignment-graph.md) | 05, 06, 08 | `role_assignment` with `reports_to` pointing at assignments, cycle rejection, lead-faculty mapping. |
| 10 | [Identity-separated read views](E0-10-identity-separated-views.md) | 08, 09 | Three database roles so instructor screens physically cannot read identity, while Care keeps an audited door; first §4.1 invariants; invariant suite becomes unskippable. Also closes the two holes in E0-08's identity marker and carries E0-09's `search_path` rule into every view. |
| 11 | [Authorization skeleton](E0-11-authz-skeleton.md) | 09, 10 | The `services/authz.py` chokepoint, role grain, sibling-lead isolation; transitive union deliberately deferred to E9. Decides where two rules E0-09's schema does not enforce live: edge direction by role, and one lead per course. |
| 12 | [AI output contracts and prompt layout](E0-12-ai-contracts.md) | 01 | One Pydantic contract per §7.4 task, versioned prompt directory, contracts usable as eval fixtures. |
| 13 | [AIGateway shell and one working round-trip](E0-13-ai-gateway-roundtrip.md) | 04, 12 | Single-shot gateway, comment validity end to end, fail-open on timeout, append-only classification rows. |
| 14 | [Mock LMS: JWKS and LTI 1.3 launch](E0-14-mock-lms-launch.md) | 02, 08 | Platform-side launch with per-run issuer keys and a signed `id_token`. |
| 15 | [Mock LMS: NRPS, AGS, and seed data](E0-15-mock-lms-nrps-ags.md) | 14 | Paged roster service, line items and score posting, seed courses with mid-term adds and drops. |
| 16 | [Mock OIDC identity provider](E0-16-mock-idp.md) | 02, 08 | Discovery, authorize, token, JWKS, PKCE, seeded leadership, Care, and admin users. |
| 17 | [Demo seed script](E0-17-seed-script.md) | 07, 09, 15 | Idempotent demo institution including the assistant dean, a two-hat person, and sibling leads. |
| 18 | [E0 exit: both doors, end to end](E0-18-e0-exit-smoke.md) | 11, 13, 15, 16, 17 | First Playwright paths through launch and web login; turns on the e2e gate; E0 exit checklist. |
| 19 | [Compose credential surface](E0-19-compose-credential-surface.md) | 02, 03 | **Batch G.** Four routes to the ADR 0009 bound — host-mount allowlist, named volumes resolved through `driver_opts`, literal values in `.env.example`, unnormalised bind sources — plus the ADR for E0-03's three closed-set rules. Already one coherent batch; nothing moved. |
| 20 | [Gate fidelity](E0-20-gate-fidelity.md) | 04 | **Redistributed — not built as written.** Its measurements stay here and its items are now 33, 36 and 37. Read it for the mutation tables, not for the work. |
| 21 | [Review debt from E0-05](E0-21-review-debt.md) | 05 | **Redistributed — not built as written.** Item 1 is now 35, item 2 is now 37. Keeps the record of Todd's `course.lms_title` decision and its three-part cost. |
| 22 | [Two spec questions from E0-05's review](E0-22-spec-questions-from-e0-05.md) | 05 | **Both decided and both spec edits landed 2026-08-18.** Now a small build ticket: the constraint enforcing one institution per deployment. §4.1 item 7's test is E4's. |
| 23 | [A spec question for E1: what triggers the first roster pull](E0-23-spec-question-first-roster-pull.md) | none | **Closed 2026-08-18.** SPEC §7.3 carries the answer. The column that stores the service address is E1's, built with the sync that reads it. |
| 24 | [Review debt from E0-07 and E0-08](E0-24-review-debt-from-e0-07-and-e0-08.md) | 07, 08 | Item 2 is now 35. Item 4 is Todd's. Items 1 and 3 leave the epic — see the carried-out table. |
| 25 | [Review debt from E0-09, E0-12 and E0-14](E0-25-review-debt-from-e0-09-to-e0-14.md) | 09, 12, 14 | Item 1 is now 36; items 2 and 3 are now 37; items 4 and 6 are **closed**. Item 5 leaves the epic. Keeps the complete index of what the three reviews produced. |
| 26 | [Review debt from E0-10](E0-26-review-debt-from-e0-10.md) | 10 | **Nothing moved — nothing here batches.** Item 1 is a live gap in SPEC §4's logging guarantee; the mechanism was decided on 2026-08-18 — the reveal returns nothing until a separately committed record exists — and it must land before **E10** opens the Care queue. Items 2 to 4 leave the epic with E10. |
| 27 | [Review debt from E0-11](E0-27-review-debt-from-e0-11.md) | 11 | **Redistributed — not built as written.** Item 1 is now 35, item 2 is now 34, item 3 is **closed**. Keeps the record of E0-11's round, including the invented-statements note. |
| 28 | [Review debt from E0-15](E0-28-review-debt-from-e0-15.md) | 15 | **Batch E.** Eight items in `mock-lms/app/`, each with a reproduction in PR #31. Item 6 is Todd's and changes what the batch costs; item 8 is **closed**. |
| 29 | [Review debt from E0-13](E0-29-review-debt-from-e0-13.md) | 13 | Items 1a and 1b are Todd's; 4b and 4c are now 36; item 3 is **closed**. Item 4a stays as a recorded decision; items 2 and 5 leave the epic. |
| 30 | [Review debt from E0-16](E0-30-review-debt-from-e0-16.md) | 16 | **Batch F.** RFC 6749 §4.1.2.1 error redirects, which E1's callback error branch and E0-18's Playwright path both need and neither can reach, plus ADR 0062's three limits, the Compose redirect URI E0-18 settles, and a strictness choice to affirm. |
| 31 | [Review debt from E0-17](E0-31-review-debt-from-e0-17.md) | 17 | **Item 1 blocks 18** — the `lti_platform` row for the mock LMS, which cannot be added carelessly without falsifying ADR 0038. Item 2 is Todd's; items 3 and 4 are now 37; item 5 is **closed**. |
| 32 | [Three gate gaps the reviewer self-test found](E0-32-gate-gaps-the-selftest-found.md) | 10 | **Redistributed — not built as written.** Item 1 is now 36; items 2 and 3 are now 34. |
| 33 | [Assert the database objects `alembic check` never looks at](E0-33-catalog-drift-assertions.md) | 08, 10 | **Batch A.** One mechanism — read the object out of the catalog and compare — covering generated-column expressions, check-constraint expressions, exclusion constraints, roles, grants, views and function owners. Carries E0-20 items 3, 3a and 3b. |
| 34 | [A view file that reads identity must fail on that ground](E0-34-view-file-identity-guards.md) | 10, 11 | **Batch B.** A `views_sql/*.sql` file joining `user_identity` passes the identity invariant vacuously and is caught only by a sweep whose message points at `public.` prefixes. Carries E0-32 items 2 and 3 and E0-27 item 2. |
| 35 | [The writer nobody routed, and the column nobody marked](E0-35-the-writer-and-the-marker-nobody-routed.md) | 07, 11 | **Batch C.** Three rules held by a docstring with nothing to notice a new violation. Carries E0-21 item 1, E0-24 item 2 and E0-27 item 1, and makes the sweep-versus-hook choice all three declined. |
| 36 | [Gates that report green over something they did not look at](E0-36-ci-gate-fidelity.md) | 04 | **Batch D.** Five items in `ci.yml`, `scripts/ci/` and the `Makefile`, including the aggregate `CI` check that prints "All gates green" over a real `migration-drift` failure. Carries E0-20 items 1 and 2, E0-32 item 1, E0-25 item 1 and E0-29 items 4b and 4c. Produces two pull requests. |
| 37 | [Seven small corrections](E0-37-small-corrections.md) | 05, 13, 17 | **Batch H.** One line to twenty each, batched because tracking them costs more than fixing them. Carries E0-20 item 4 and its two smaller entries, E0-21 item 2, E0-25 items 2 and 3, and E0-31 items 3 and 4. Item 1 is the only one with a confidentiality consequence. |

## Dependency graph

```
01 ── 02 ──┬── 03
           └── 04 ──┬── 05 ──┬── 07 ───────────────┐
                    ├── 06 ──┘                     │
                    └── 08 ──┬── 09 ── 10 ── 11 ───┼── 18
                             └── 14 ── 15 ─────────┤
                                                   │
01 ── 12 ── 13 ─────────────────────────────────── ┤
02 ── 16 ───────────────────────────────────────── ┤
07, 09, 15 ── 17 ───────────────────────────────── ┘

                     31 item 1 ─────────────────── ┘   (the only blocker on 18)

08, 10 ── 33        Batch A — catalog comparison
10, 11 ── 34        Batch B — view files that read identity
07, 11 ── 35        Batch C — the writer and the marker sweeps
04 ── 36            Batch D — the pipeline itself
02, 03 ── 19        Batch G — Compose credential surface
15 ── 28            Batch E — mock LMS conformance
16 ── 30            Batch F — mock IdP error redirects
05, 13, 17 ── 37    Batch H — seven small corrections

20, 21, 27, 32      redistributed; read for their measurements, do not build
22, 23              Todd's, and 22's first question has an E4 deadline
24, 25, 26, 29, 31  partly moved; what is left is decisions and records
```

Strictly sequential through 04. After that, three chains run independently and
can be built in any interleaving: the schema chain (05 → 09 → 11), the AI chain
(12 → 13), and the mock-platform chain (14 → 16). Ticket 17 needs the schema
chain and the mock LMS; ticket 18 needs everything.

## How the remaining work is batched

Tickets 19 to 32 were written one per source ticket, which is the right way to
capture a review round and the wrong way to build. Fourteen tickets, but the work
lands in **seven places in the code**, and three separate tickets kept arriving at
the same test module. Tickets 33 to 37 carry the items that cross a ticket
boundary; 19, 28 and 30 were already batches and keep their numbers.

**Every source ticket says, item by item, where its items went.** Read the
`## Status` block at the top of any of 19 to 32 rather than inferring it from
here.

| Batch | Ticket | Where the work is | Size |
|---|---|---|---|
| A | 33 | a new integration module reading `pg_catalog` | medium |
| B | 34 | `views_sql/` and the identity-marker sweep | small |
| C | 35 | a sweep in the shape of the read-side one | medium |
| D | 36 | `ci.yml`, `scripts/ci/`, the `Makefile` | medium |
| E | 28 | `mock-lms/app/` | medium |
| F | 30 | `mock-idp/app/` | medium |
| G | 19 | `tests/unit/test_compose_stack.py` and its neighbour | medium |
| H | 37 | seven files, one to twenty lines each | small |

**Suggested order: A and B first, as one sitting.** They are the same subject —
the identity separation the whole of §4.1 rests on has no assertion over the
objects that implement it — they are both cheap, and B is the smaller half of a
hole A does not reach. Then **31 item 1 and then 18**, which is the only path to
the epic actually exiting. Everything after that can land in any order.

**A and B are the two batches where the thing being protected is the
confidentiality model rather than a convenience.** Two of A's mutations —
`GRANT SELECT ON public.user_identity TO pulse_app` and `ALTER ROLE pulse_care
SUPERUSER` — are each one statement that voids the whole scheme with `alembic
check` reporting clean.

### One blocker

**E0-31 item 1 is the only item in 19 to 37 that blocks the E0 exit.** E0-18
drives a real launch from the mock LMS and no `lti_platform` row trusts it,
because E0-17 deliberately registered a fictional platform instead so that ADR
0038's argument would survive. Adding that row carelessly is what makes ADR 0038
wrong, so it has to be done by somebody who has read why it does not exist.

### Deadlines that are not blockers

- **E0-30 item 1** is not a blocker and is the worst to defer. E1's OIDC callback
  has an error branch this mock makes unreachable, so leaving it means E1 ships
  that branch untested or does not ship it — and the case it handles, the user
  cancelling, is the one that actually occurs.
- **E0-35 and E0-28 item 1** both land on E1's roster sync from opposite sides.
  That sync is the first code to write all four relations the E0-11 chokepoint
  refuses, and it is also the code that reads the enrollment windows E0-15 puts
  on every seeded member — windows no real platform supplies.
- **E0-22 question 1** is a confidentiality rule that is currently unenforced,
  and E4 builds the reports it governs.
- **E0-26 item 1** is a measured gap in SPEC §4's logging guarantee rather than
  hardening: a caller holding the Care credential who rolls back keeps the
  student's name and leaves no audit row. Nothing in E0 opens that door; it has
  to close before E10 builds the queue that calls it.
- **E0-23** blocks nothing here and E1's sync cannot be built without it.

## Carried out of E0

Every item that leaves this epic, with the epic that owns it. This table exists
because [E0-26](E0-26-review-debt-from-e0-10.md) item 5 is the finding that a
deferral recorded only in the ticket that deferred it is a deferral nobody picks
up.

| Item | Owner | Why it cannot be done here |
|---|---|---|
| E0-24 item 1 — `jwks_url` is credential-equivalent and unconstrained | **E1** | E1 writes and fetches the column and is the only code positioned to say what a legitimate value looks like |
| E0-24 item 3 — re-derive a section when its term's map is edited | **E2 / E11** | the owners ADR 0021 and ADR 0018 already name |
| E0-25 item 5 — the mock LMS cannot mint a deliberately wrong launch | **E1** | tool-side launch validation is E1's, and E0-14 defined no interface for a bad launch deliberately |
| E0-26 item 2 — the reveal writes no conflict-of-interest marking | **E10** | the wide case needs E9's purview union; the narrow case wants the queue that reads it |
| E0-26 item 3 — the acting person is a parameter, not a property of the connection | **E10** | the first thing with a request-bound actor to bind |
| E0-26 item 4 — the Care sweep misses the module's own entry point | **E10** | the rule is "only the Care queue imports it", and the queue is E10's to write |
| E0-29 item 2 — three rows of ADR 0056's taxonomy nothing asserts | **out of E0** | DNS failure, TLS handshake failure and pool timeout are not producible from a loopback stub |
| E0-29 item 5 — `run_task` from inside a running event loop | **E2** | E2 owns whether ADR 0013's `def` handler convention stays a convention |
| SPEC §4.1 item 1 — no student-visible path exposes another section | **E2** | the first epic with a student-visible path, and the scoping that gives "another section" its meaning |
| Database TLS on both engines | **E13** | the operator guide owns it; it matters before a managed or remote Postgres |

## Decided

All thirteen open questions were answered by Todd on **2026-08-18**, and the four
spec edits they required **have landed** in the same day's work. Nothing below is
an implementer's call and nothing below is still open. The **Spec edit** column
says which answers needed one and where it went.

| # | Question | Decision | Spec edit |
|---|---|---|---|
| E0-31 item 1 | How is the mock LMS registration kept out of a deployed environment? | **Reuse the seed script's development-environment guard.** Register the mock behind the same guard `scripts/seed.py` already uses, and amend ADR 0038 to name that guard as what enforces its argument. | no |
| E0-35 | Sweep the source, or hook the session? | **Sweep the source.** A test that reads our own modules and fails when one writes `course`, `section`, `enrollment` or an `INSTRUCTOR` `role_assignment` without naming `guard_write`. Record what a syntactic sweep cannot see, the way ADR 0062 does for the mock-idp gate. | no |
| E0-30 item 1 | Does the mock identity provider learn RFC 6749 §4.1.2.1 error redirects? | **Yes, implement them.** About 40 lines plus tests, at the split point that already exists in `begin()` after `redirect_uri` validates. A refusal must arrive as a redirect carrying `error` and the `state` that was sent, and a test must fail if it reverts to a page. | no |
| E0-28 item 6 | Does the mock LMS learn to authenticate now? | **Not now.** Its four moving parts go into E1's ticket so whoever builds the roster sync meets them before writing the client rather than after. E0-28's other eight items proceed without it. | no |
| E0-22 q1 | Benchmark minimum — every figure, or only drawn lines? | **Every figure computed from a comparison set**, not only a drawn line. | **landed** — §4.1 item 7, §5.1 rewritten to point at it. Its *test* is E4's. |
| E0-22 q2 | Does one deployment serve exactly one institution? | **Yes, and enforce it.** A constraint permitting at most one `institution` row, which makes global and institution-scoped uniqueness the same rule. | **landed** — §8, with ADR 0017 amended. The *constraint* is E0-22's own remaining work. |
| E0-23 | What triggers the first roster pull? | **Any instructor or leadership launch**, and the roster service address is stored from that launch. A student launch does not trigger one. Every later scheduled sync works from the stored address, and a never-synced section is visible as such. | **landed** — §7.3, §2.1 points at it. The column and its sync are E1's. |
| E0-26 item 1 | Which mechanism closes the rollback that keeps a name and leaves no audit row? | **Restructure the reveal so it returns nothing until a separately committed record exists.** Not `dblink`, not a loopback `postgres_fdw` — both put a database credential inside a `SECURITY DEFINER` function, which is a new privilege surface. Its ADR says what the chosen shape costs. | no |
| E0-29 item 1a | Is cleartext to an off-machine model endpoint acceptable? | **No — refuse it.** Require an encrypted transport whenever the model is on another host, with or without a credential. A cluster deployment terminates TLS at the model or runs it alongside the app. `README.md` and `.env.example` change wherever they document the current allowance. | no |
| E0-29 item 1b | Do HTTP 429 and 500 belong in the fail-open set? | **No — affirmed as built.** A rate limit is a capacity decision an operator must see and a 500 means our request is the problem; flooring either hides a condition that never resolves. The reasoning goes into ADR 0056 so it stops being an open row. | no |
| E0-31 item 2 | `design/`'s 27 course numbers versus SPEC §8's bands. | **The design corpus is illustration.** It is not a source of seedable data and says so, so nobody reconciles it against §8 or seeds from it. No renumbering. | no |
| E0-24 item 4 | Does the spec grow a real summer start-letter map? | **No.** The invented constants stay, marked as the test suite's own choice. **The gap at position 6 survives any edit** — a contiguous map is satisfiable by a range computed from the term's length, which is the wrong implementation those tests exist to refuse. | no |
| E0-25 item 6 | Two spec lines describe things that no longer exist. | **Correct both.** | **landed** — §8's scope columns and core-table list, plus three §13 module comments that were wrong the same way. |

**All four spec edits have landed**, so no answer here is waiting on a document.
What two of them left behind is *code*, and it is owned:

- **The single-institution constraint is E0-22's**, and it is that ticket's whole
  remaining scope. §8 states the rule; nothing yet enforces it.
- **§4.1 item 7's test is E4's**, because the reports carrying comparison-set
  figures do not exist yet. §4.1's preamble now names item 7 and item 1 as the
  two invariants that carry no assertion, rather than claiming all seven do.
- **E0-23's stored service address is E1's**, built with the sync that reads it.

Two answers still want an existing record amended in the pull request that
implements them: **ADR 0038** for E0-31 item 1, and **ADR 0056** for E0-29 items
1a and 1b. ADR 0017 was amended with E0-22's spec edit and needs nothing further.

## What the built tickets settled

Tickets 01 to 04 were written before the code existed, and building them decided
things the later tickets were written without knowing. Those decisions are now
load-bearing, and most of them fail in a way that does not point at itself. This
section is the short list; the tickets it affects carry a pointer to it rather
than a copy, because a copy in six places drifts in five.

**A model module must be imported in `backend/app/models/__init__.py`, in the
same change that adds it.** `migrations/env.py` autogenerates against
`Base.metadata`, and a table whose module nobody imported is not on that
metadata. So `alembic check` reports no drift, the migration nobody wrote is
never missed, and the table does not exist in any deployed database. Nothing
fails at the time; E0-04 left the rule in that file's docstring, and it is the
same class of silence [E0-33](E0-33-catalog-drift-assertions.md) and
[E0-36](E0-36-ci-gate-fidelity.md) exist to break — a gate reporting green over a
check it did not perform.

**Model modules import `Base` from `app.models.base`, never from `app.db`.**
`app.db` re-exports `Base` and that is the import the *application* writes, but
it also builds an engine out of `Settings()` when imported, which needs
`AI_PROVIDER_BASE_URL` and four other variables that have nothing to do with a
schema. CI's `migration-drift` job and the testcontainers fixture both supply the
database variables alone. A model module reaching `Base` through `app.db`
therefore works on a developer's machine, where `.env` has everything, and breaks
in CI. The reasoning is in `backend/app/models/base.py`'s docstring.

**Constraints are named by the convention, not by hand.** `Base.metadata` carries
`NAMING_CONVENTION`, so autogenerate renders `op.f('pk_…')` and names are stable
across regenerations. Do not hand-name a constraint to match a preferred style —
`alembic check` will churn. Watch the 63-byte Postgres identifier limit when
choosing table and column names, since the convention's templates concatenate.

**The database fixtures already exist.** `tests/conftest.py` provides
`postgres_container`, `provisioned_database`, `migrated_database`,
`empty_database`, `migrated_engine`, `db_session` and `application_engine`. A
schema ticket writes tests against these rather than standing up its own
Postgres. The fixture provisions the same two-role shape a deployment has, so a
test that passes under privileges production lacks is a test that fails.

**Migrations run as `DB_SUPERUSER`, never as the application role** ([ADR
0009](../../adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md),
[ADR 0012](../../adr/0012-the-migration-environment-builds-its-own-superuser-connection.md)).
`env.py` takes the address from `DATABASE_URL` and the identity from the
superuser pair. No ticket needs to add a variable for this. `make migrate` runs
on your host, so `DATABASE_URL` has to name `localhost` rather than the Compose
service — `README.md` says where.

**An `.env.example` entry needs a reader, or its test fails.** An entry earns its
place because an `app.config.Settings` field resolves to it, or because a Compose
file interpolates it as `${NAME}` ([ADR
0008](../../adr/0008-env-has-two-readers-and-the-database-credential-is-split.md)).
A variable read only by something else — a script, a mock service that is not a
Compose service — cannot be documented there as things stand, and
`tests/unit/test_env_example_sync.py` will say so. Tickets 08, 13 and 16 all add
configuration and should expect this.

**The application role is `pulse_app`, and a read-path test must connect as it**
([ADR 0001](../../adr/0001-identity-separation-by-database-role.md), E0-10).
From E0-10 the migration grants `SELECT` on the read views to `pulse_app` and
nothing at all on `user_identity`, so *which role a fixture authenticates as* is
now the difference between a test that can detect a missing grant and one that
cannot. `tests/conftest.py`'s `application_engine` provisioned and connected as
`pulse_test_app` — a name chosen in E0-04, when no grant existed for it to be
wrong about — which held none of those grants, so an assertion made over it was
an assertion about a role holding nothing and passed for the wrong reason
(`docs/MISTAKES.md` entry 3). **E0-10 changed it to `pulse_app`**, one line, and it
works because the fixture creates the role before the migration runs and the
migration's `CREATE ROLE` is guarded, exactly as on a Compose volume. Two things
follow for anyone writing a read-path test: `application_engine` is now evidence
about a grant, and
`test_the_suites_application_connection_authenticates_as_the_granted_role` in
`tests/integration/test_identity_grants.py` is what keeps the fixture's name and
the migration's name from drifting apart again — they are two constants in two
files and nothing else would notice. E0-10's own grant tests reach both runtime
roles with `SET ROLE` from the bootstrap session, because `pulse_care` has no
login credential in the fixture and because a control and the refusal it
qualifies then sit in one transaction.

**Adding a read view means adding SQL to `backend/app/views_sql/` and an
invariant test** (SPEC §13, [ADR
0041](../../adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md)).
A view is read with its *owner's* privileges, so no grant protects it: a view
that reads an identity column hands that column to every role that may read the
view. `CONTRIBUTING.md` has the rule; the short version is a new versioned
`.sql` file, never an edit to one a migration already executed, every relation
schema-qualified, and a `@pytest.mark.invariant` test for the §4.1 rule the view
is subject to.

**Only `app/services/safety.py` may obtain a `pulse_care` session** ([ADR
0042](../../adr/0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md)).
The pool is bound to the code path, not to the actor, because §2.1 permits one
person to hold a Care assignment and a teaching assignment at once. A module that
imports, calls or attributes a Care session fails
`tests/unit/test_care_session_is_bound_to_the_care_service.py` by name. Care's
route to identity is `reveal_identity`, which checks the actor and calls a
`SECURITY DEFINER` function that checks the actor again and writes the audit row
in the same transaction.

**The session is synchronous** ([ADR
0013](../../adr/0013-the-database-session-is-synchronous.md)). Handlers that
touch the database are written `def`, not `async def`, and FastAPI runs them in
its threadpool. The same session serves Celery tasks and `pylti1p3`, both of
which are synchronous.

## How CI tightens

Most CI gates ship tolerant because nothing they check exists yet — see
[ADR 0002](../../adr/0002-ci-gates-ship-tolerant.md) for why, and for the cost
that choice carries. Each becomes enforcing in a specific ticket, and landing
that ticket includes removing its tolerance:

| Gate | Becomes enforcing in |
|---|---|
| ruff, mypy, pip-audit, license check, pytest | 01 (and see below — its last tolerance went in 04) |
| Docker build and Compose health (`api`) | 02 |
| Compose health (`api`, `worker`, `beat`) | 03 |
| Compose health (`mock-lms`) | 14 |
| Compose health (`mock-idp`) | 16 |
| migration drift | 04 |
| §4.1 invariant suite — no skips permitted | 10 |
| Playwright e2e | 18 |
| AI eval floors | E2, not E0 — the last tolerance to survive this epic |

The pytest row moved from 04 to 01 and is worth a word, because it tightened in
two steps rather than one. It was never gated on a flag; it was gated on the
`detect` job finding `tests/unit/test_*.py`, and ticket 01 shipped that
directory, so the gate went live the moment the first test landed. What that
left was a gate that could switch *itself* off again — delete the directory,
break collection, and `pytests` goes back to `false` with a green check. Ticket
04 removed the condition, so both the pytest and migration-drift jobs now run
unconditionally, and the `detect` job no longer probes for either.

The frontend gates (`tsc`, `eslint`, production build, bundle budget) stay
tolerant through all of E0. No frontend exists until E1.

## Notes on the decomposition

Where this differs from the ticket list in §14.3, and why:

- **"repo+CI" is already done** and is not a ticket here.
- **"Compose+Dockerfiles" is split** into 02 and 03. The Compose file and the
  Celery runtime are separately reviewable, and the health-check argument list
  in CI changes in a way worth seeing on its own.
- **"core schema" is split four ways** — 05, 06, 08, 09 — plus 10 for the views.
  It is by far the largest ticket in §14.3, and 09 in particular carries the
  supervision graph, which decides whether purview can be computed correctly at
  all.
- **The section-code parser (07) is its own ticket** rather than part of the
  term schema. It is pure logic with heavy property testing, which is a
  different kind of session from writing migrations.
- **"AIGateway shell + task contract models" is split** into 12 and 13, because
  the contracts are a design decision worth settling before an implementation
  pulls them into a shape.
- **"mock LMS" is split** into 14 and 15. Launch signing and the Advantage
  services are independently testable, and 15 is where NRPS paging lands, which
  is a named per-platform deviation in §7.3.
- **18 is new** — §14.3 implies E0's exit criterion but lists no ticket that
  proves it. Without it the e2e gate would stay tolerant into E1.
- **19 is new, and came out of building 03** rather than out of §14.3. Five
  reviewer passes on the E0-03 pull request found route after route by which a
  future edit could hand an application container the Postgres superuser
  credential that ADR 0009 exists to withhold from it. Most were closed there;
  the four that remained are a coherent subject of their own and were splitting a
  Celery ticket in half, so they became a ticket, along with the ADR E0-03 owes
  for the three constraints it imposed on anyone editing a Compose file. It adds
  no behaviour and blocks nothing.

Where a branch name here differs from the *Ticket breakdown* line under E0 in
SPEC §14.3, or from the three illustrative names in `CONTRIBUTING.md`'s diagram,
these names win. §14.3 lists eight groupings, not twenty-five branches.
