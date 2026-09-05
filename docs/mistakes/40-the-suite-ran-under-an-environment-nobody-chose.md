# Entry 40. The suite ran under an environment nobody chose, and it was a different one in CI

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*4 instances recorded. The three most recent are here — the two blocks below,
newest first, and E1-11's with the rule. The fourth is the founding incident,
E1-10 on PR #105, which is where its diagnosis now lives (it was carried here in
full until FIX-03 trimmed this file to the three most recent, as
`docs/MISTAKES.md` asks): CI found ten tests failing that had passed locally
because `backend/migrations/env.py` had loaded the developer's `.env` into the
pytest process, from three separate fixtures, and the fix was a whole-environment
snapshot-and-restore around each of them plus a test stating the environment its
claim was about. The rule below is what it produced.*

*(2026-09-05, E3-06 on PR #172, and the recurrence this file's structural fix
was written for. A fixture imported the jobs module without declaring its
environment; it passed locally and every local round, and went red on a bare
xdist worker in CI. It was repaired the declared way, and the class it belongs to
was given its own ticket — FIX-03 — rather than a fourth instance of the same
repair. **Not counted as a catch**, for the reason E1-11's was not: CI found it,
the entry did not stop it.)*

*(**A catch**, writing E2-07's tests, 2026-09-01. The ticket points
`.env.example`'s `AI_PROVIDER_BASE_URL` at the in-stack mock, and a deployment
refuses that value by two new rules. Acting on this entry, every new
environment-sensitive test states the environment it runs under in its own
fixture chain rather than inheriting whatever the process held — and stating it
is what exposed that roughly twenty-seven existing modules build `Settings`
under a non-development environment and would have stopped in their own setup
on a rule that is not their subject. The repair went into the two shared
fixtures those modules already request, in the same tests-first round, instead
of surfacing later as unexplained reds in CI's differently-ordered workers.)*

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
inferring it from the fixtures that should have set it. In E1-10 the inference
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
fixture. The process lesson underneath it: **a local run reads the documented
values off the developer's machine — the shell exports them, and
`backend/migrations/env.py` loads `.env` into the pytest process the first time a
fixture applies a migration — while CI's pytest gate has neither, so a green
local `make test` does not prove that gate green.** Before pushing, run
`make test-as-ci`: it moves `.env` aside, unsets every name `.env.example`
documents, and runs the same `test` gate in what is left, which is the one local
run that shares CI's configuration. That command is FIX-03's, and until it
existed the same reproduction was a by-hand dance that nobody ran. Not counted
as a catch: CI caught it, the gate did not.
