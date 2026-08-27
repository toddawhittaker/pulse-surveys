# Entry 40. The suite ran under an environment nobody chose, and it was a different one in CI

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*1 instance recorded.*

*(E1-10, found by CI on PR #105 after three verified build rounds, two mutation
batteries, and repeated green local runs of the full suite.

The ten in-band cases of
`tests/integration/test_launch_provisioning_defects.py::test_a_course_number_inside_spec_8s_bands_is_provisioned`
assert that an ordinary staff launch provisions with no defect recorded. They
drive the writer directly, and the writer reads `ENVIRONMENT` from the process
per call: absent counts as a deployment, deliberately, and under a deployment's
name the registration-address rules refuse the mock platform's cleartext
`http://mock-lms:8000/...` roster address. Nothing in those tests' fixture
chain set `ENVIRONMENT` — and they passed locally anyway.

They passed because of a leak. The session-scoped `migrated_database` fixture
runs `alembic upgrade head` in process, which executes
`backend/migrations/env.py` — a documented third reader of `.env` — and that
file calls `load_dotenv(<repo root>/.env, override=False)`. The call writes the
developer's whole `.env`, `ENVIRONMENT=development` included, into `os.environ`
for the rest of the pytest session; the fixture's own restore covers only the
three variables it set itself. CI has no `.env` file: nothing leaked,
`ENVIRONMENT` stayed unset, the rules were in force, and all ten cases failed
with a `roster_address_refused` defect no local run had ever shown. The leak
had three sites, not one — the same `env.py` runs again for every test that
invokes an Alembic command itself (`alembic_config_pointed_at`), and again for
the demo-seed database — and `monkeypatch` can undo none of them, because it
only knows the names it set.

The diagnosis had a false start worth keeping. With the variable explicitly
unset the failing test still passed locally, which read as disproof of the
environment theory; a probe on the refusal call showed `ENVIRONMENT=development`
present at call time regardless, set during `migrated_database`'s setup.
Reproduction was `ENVIRONMENT=` — the empty string, which `load_dotenv` does
not override — and that one spelling produced CI's exact failure on a developer
machine.

The fix was two halves, both in the fixtures. All three Alembic-running sites
now snapshot and restore the whole of `os.environ`
(`whole_environment_restored` in `tests/fixtures/database.py`), so what
`migrations/env.py` loads cannot outlive the command. And `registered_platform`
pins the development name itself, so the ordinary-path tests state the
environment their claim is about instead of inheriting whichever one the
process happened to hold. Disabling only that pin line reproduces all ten CI
failures; restoring it turns them green — measured, not assumed.

The review re-pass had in fact priced this area: its deferred LOW says
`_environment()` reads `os.environ` where every other reader uses `Settings`,
and named "a dotenv-only dev run refusing the mock's address" as the cost. The
cost arrived mirrored — a no-dotenv CI run refusing the mock's address — and
what nobody priced was that the *tests'* environment was itself an accident of
the dotenv leak.)*

## The rule

**A test's environment is part of its claim.** A test whose subject reads the
process environment must state the value it runs under, in its own fixture
chain — a green that depends on what the developer's machine happened to export
is a claim about that machine, not about the code.

The wider class: **anything run in process inside a fixture brings its whole
startup behaviour with it, for the rest of the session.** A tool written to be
a process — one that loads `.env`, sets a locale, registers handlers, mutates
any process-wide state — makes its startup part of every later test when a
fixture hosts it in the test process. Wrap it in a full snapshot-and-restore of
the state it mutates, or run it as the process it was written to be. And the
restore must cover state the fixture did not set: `monkeypatch` and an
enumerated restore both undo only the names they were told about, which is
exactly what a foreign loader does not tell them.

When a suite is green locally and red in CI, diff the *processes*, not the
code: measure what each holds at the failing call with a probe, rather than
inferring it from the fixtures that should have set it. Here the inference
("nothing sets it, so it is unset in both") was wrong in both directions at
once — and note that unset and empty behaved differently, so reproducing
"absent" needed the spelling the loader would not override.

**Instance, 2026-08-27 (E1-11, PR #107's first CI run).** The same shape, a
new door in. E1-11 gave `provision_from_launch` a `settings` parameter, so
`ProvisioningService.settings` built a full `Settings()` where E1-10's tests
never reached one — and the `provisioning` fixture depended on nothing, so the
documented variables were never laid down. Sixteen of E1-10's course-number
tests went red in CI with `ConfigurationError: DATABASE_URL — not set` (and
every other variable), while every local run stayed green off `.env`. The fix
made the fixture depend on `configured_env`, like every other Settings-building
fixture. The process lesson underneath it: **the local `make ci` gate sources
`.env`, and CI's pytest gate has none, so a green `make ci` does not prove the
pytest gate green.** Before pushing, run the pytest gate once with `.env` moved
aside — that is the only local run that shares CI's configuration. Not counted
as a catch: CI caught it, the gate did not.
