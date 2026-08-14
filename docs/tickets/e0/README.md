# E0 — Foundations: build order

Twenty tickets decomposing the E0 tickets in SPEC §14.3. Each is sized for a
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
| 10 | [Identity-separated read views](E0-10-identity-separated-views.md) | 08, 09 | Three database roles so instructor screens physically cannot read identity, while Care keeps an audited door; first §4.1 invariants; invariant suite becomes unskippable. |
| 11 | [Authorization skeleton](E0-11-authz-skeleton.md) | 09, 10 | The `services/authz.py` chokepoint, role grain, sibling-lead isolation; transitive union deliberately deferred to E9. |
| 12 | [AI output contracts and prompt layout](E0-12-ai-contracts.md) | 01 | One Pydantic contract per §7.4 task, versioned prompt directory, contracts usable as eval fixtures. |
| 13 | [AIGateway shell and one working round-trip](E0-13-ai-gateway-roundtrip.md) | 04, 12 | Single-shot gateway, comment validity end to end, fail-open on timeout, append-only classification rows. |
| 14 | [Mock LMS: JWKS and LTI 1.3 launch](E0-14-mock-lms-launch.md) | 02, 08 | Platform-side launch with per-run issuer keys and a signed `id_token`. |
| 15 | [Mock LMS: NRPS, AGS, and seed data](E0-15-mock-lms-nrps-ags.md) | 14 | Paged roster service, line items and score posting, seed courses with mid-term adds and drops. |
| 16 | [Mock OIDC identity provider](E0-16-mock-idp.md) | 02, 08 | Discovery, authorize, token, JWKS, PKCE, seeded leadership, Care, and admin users. |
| 17 | [Demo seed script](E0-17-seed-script.md) | 07, 09, 15 | Idempotent demo institution including the assistant dean, a two-hat person, and sibling leads. |
| 18 | [E0 exit: both doors, end to end](E0-18-e0-exit-smoke.md) | 11, 13, 15, 16, 17 | First Playwright paths through launch and web login; turns on the e2e gate; E0 exit checklist. |
| 19 | [Compose credential surface](E0-19-compose-credential-surface.md) | 02, 03 | Four routes to the ADR 0009 bound — host-mount allowlist, named volumes resolved through `driver_opts`, literal values in `.env.example`, unnormalised bind sources — plus the ADR for E0-03's three closed-set rules. |
| 20 | [Gate fidelity](E0-20-gate-fidelity.md) | 04 | Gates that report green while the thing they detect is happening: the aggregate `CI` check blind to a `migration-drift` failure, the drift job's two-role shape unasserted, a generated column's expression drifting unseen, and `echo=False` not being what keeps SQL out of the log. The server-default half closed in 05. |

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

02, 03 ── 19        (independent; blocks nothing)
04 ── 20            (independent; blocks nothing)
```

Strictly sequential through 04. After that, three chains run independently and
can be built in any interleaving: the schema chain (05 → 09 → 11), the AI chain
(12 → 13), and the mock-platform chain (14 → 16). Ticket 17 needs the schema
chain and the mock LMS; ticket 18 needs everything. Tickets 19 and 20 hang off 03
and 04 and block nothing — both harden tests rather than adding behaviour, so
they can land any time afterwards and neither is on the path to the E0 exit.

One caveat on 20, because "blocks nothing" is not quite "no hurry": its third
item was `alembic check` being blind to server-default drift, and E0-05 is where
the first server defaults landed. **E0-05 closed that item** — `env.py` now sets
`compare_server_default=True` on both paths — so 20 is down to three, and it
gained a narrower fourth in the same place: a *generated* column's expression can
still drift with `alembic check` green, because Alembic warns rather than
failing. Details in E0-20 item 3.

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
fails at the time; E0-04 left the rule in that file's docstring, and E0-20's
"gate fidelity" subject is exactly this class of silence.

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

The illustrative ticket names in `CONTRIBUTING.md` predate this file. Where the
two differ, these ticket branch names win.
