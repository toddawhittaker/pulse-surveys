# E1 boundary fix, batch B — attempts

Branch `e1/boundary-fix-launch-door`, worktree
`.claude/worktrees/batch-b`, tests committed red at `4c67cac`. Scope: M4
(a launch with no `sub`), M7 (`refusal_page` takes no free text), H2 (the
binding survives a downgrade), R6 (already-green log guard), and two record
edits.

Every run below is
`PYTHONPATH=<worktree>/backend /home/todd/projects/pulse-surveys/.venv/bin/pytest`,
with `app.__file__` proved to be a batch-b path first (`docs/MISTAKES.md`
entry 12 and the worktree note in the orchestrator's brief).

## 1. Confirm the reds myself — done, matches the manifest exactly

`pytest` over the five touched modules, `-p no:randomly`: **10 failed, 115
passed** in 108s. The ten are the manifest's ten, name for name: the two
sub-less launch cases, the handshake case, the refusal-page body scan, the
two downgrade round trips, and the four web-door error-redirect refusals that
carry no `data-reason` marker.

Nothing failed on an import or a collection error, so every red is a test
reaching an assertion — which is what makes them statements about the code
rather than about the harness.

## 2. Reading, before writing anything

Findings that changed what I was about to build:

- **The review's H2 sentence "the fix shape already exists in-tree —
  `e2c94b6a1f70`'s downgrade preserves into a scratch table" is false.** That
  revision's downgrade *fills* `user_identity.identity_name` with a marker
  before putting a `NOT NULL` back; it creates no scratch table, and no
  migration in `backend/migrations/versions/` does (`grep` for `CREATE TABLE
  IF NOT EXISTS`, `scratch`, `preserv`, `restore` finds nothing of the kind).
  So there is no in-tree shape to copy and the preserve/restore below is
  written from scratch, in the style of the revision's own
  `BIND_EXISTING_SECTIONS` block — a `DO $$` block, so `alembic upgrade --sql`
  carries it.
- **`app.services.provisioning._record_the_launching_subject` already raises
  on an absent `sub`**, with the message "which the door it came through has
  already required". That claim is false today and M4 makes it true; the raise
  stays as the defence in depth its own docstring describes.
- **The e2e spec pins one piece of refusal copy**:
  `tests/e2e/exit-refused-launches.spec.ts`'s `REPLAY_REASON` is
  `NonceReplayedError`'s two sentences, copied whole from
  `backend/app/lti/replay_guard.py`. The M7 copy map has to carry that string
  byte for byte or the browser proof reds.

## 3. M4 — the guard, and where it goes — worked first time

`AnonymousLaunchRefused` is a `LaunchRefusedError` subclass in
`app/lti/launch.py`, and the check is step 11 of `_validate`, after the version
check and before `claim_nonce`. **Placing it there rather than in the router or
in provisioning is the whole of the work**: `verified_launch`'s existing
`except LaunchRefusedError` already logs one WARNING carrying the guard name,
consumes the in-flight handshake, and re-raises to a door that renders the
shared page with the marker. Nothing about this refusal is special-cased, which
is what the handshake test is actually asking about.

Before the nonce is spent rather than after, following the comment already on
`_validate` ("the claim is spent last, only after every other check has
passed").

Result: 5 passed (the two refusals, the two paired landings, the handshake
case). ADR 0106 written, index row added.

## 4. M7 — the page takes a guard name and nothing else — worked first time

`refusal_page(guard: str)`, with `REFUSAL_COPY` keying twelve guard names to a
constant sentence each and `DEFAULT_REFUSAL_COPY` behind them; `refused(guard)`
likewise. **`guard` is required, not optional.** Keeping it optional would have
left "a refusal page naming no guard" representable, and that state is exactly
the defect four of the ten reds were reporting.

The map is keyed by class *name*, not by class, because `app.api.deps` sits
below both doors and importing `app.lti.launch`'s guards and `app.api.auth`'s
would invert that. A guard renamed on one side falls to the default — calm
copy, rather than a `KeyError` turning a refusal into a 500 from the other
side.

The provider-error branch in `cancelled_or_refused` passes
`SessionRefusedError.__name__`. It raises no exception, so there was no
`type(refusal).__name__` to take; that name is the web door's one published
guard (ADR 0103) and the branch is a session refused — a callback the tool
cannot account for, nobody signed in.

Result: 94 passed across the new unit module, `test_chosen_landing.py` and the
whole web door module.

## 5. H2 — preserve into a scratch table, restore by key — worked first time

`section_binding_preserved (section_id uuid PRIMARY KEY, lms_context_id text
NOT NULL, lti_deployment_id uuid NOT NULL)`. The downgrade drops any leftover,
creates it, and copies every section's pair in; the upgrade restores by key
**before** `BIND_EXISTING_SECTIONS` runs — so a restored section is not
"unbound" when the backfill counts — and then drops the table, which is what
keeps `alembic check` clean at head.

Measured rather than reasoned, on a throwaway Postgres 17.11 container of my
own on port 55433 (never the shared Compose stack), provisioned with the real
`scripts/db-init/01-application-role.sh` and the CI job's own environment:

- `alembic upgrade head && alembic check` — clean.
- `alembic downgrade d7a4e1c05b93` → the scratch table is present →
  `alembic upgrade head` → the scratch table is `GONE` → `alembic check` clean
  again.

### Two mutations run against the fix, and one of them did not die

Both applied to the real file, both confirmed present with `grep` before the
run (`docs/MISTAKES.md` entry 16), both reverted with `git checkout` of a
committed file.

1. **Restore onto the wrong row** — `WHERE kept.section_id <> s.id`, which for
   two rows is exactly the swap the module's docstring names as its near miss.
   `test_a_downgrade_and_re_upgrade_gives_every_section_its_own_binding_back`
   **failed**, as it should. (The two-trip test passed, which is correct and
   worth knowing: swapping twice is the identity.)
2. **Preserve assuming it starts from nothing** — the `DROP TABLE IF EXISTS`
   removed. **Both tests stayed green.** The upgrade drops the table after
   restoring from it, so an ordinary down-up-down-up journey never meets its
   own leftovers, and that line is defence against a partial failure rather
   than the thing that makes a second trip work. My comment had claimed it was
   the latter. The line stays; the comment was corrected to say what it
   actually earns, in a refactor commit of its own.

## 6. The one whole-suite failure was the environment, not the diff

`tests/unit` + `tests/integration` under `-n 4`: **1 failed, 2062 passed**.
`test_generated_constraint_names.py` died inside `Settings()` with every
variable "not set" — `docs/MISTAKES.md` entry 40, precisely: this worktree has
no `.env`, and that test's subject reads the process environment. Re-run with
the environment stated it passes, and the whole suite is then **2063 passed**.
Not bumping entry 40's counter: it saved me an investigation, not a defect, and
the file's own rule says a detection is not a bump.

## 7. Records

Two edits were ordered and both are made: `boundary-fix-plan.md` records M7's
move from batch C to batch B with the reason, and `deferred.md` gets the
closure lines on E1-10 items 3 (the round-trip hazard behind the `count(*) = 0`
measurement) and 6 (the refusal-log entry, closed by R6).

Three more were not ordered and are entry-1 corrections to records this change
made false — flagged in the report so the orchestrator can drop any that
conflict with another batch:

- **ADR 0103** and its index row: `refusal_page`/`refused` no longer take a
  `reason` and an optional `guard`, there is no attribute-less case left, and
  the launch vocabulary is eleven subclasses rather than ten.
- **`boundary-review.md`**, H2: the "`e2c94b6a1f70`'s downgrade preserves into a
  scratch table" sentence is struck, because it does not.
- **`boundary-review.md`**, M7: re-dispositioned from batch C to batch B.
- **`boundary-fix-plan.md`**, batch B's `Touches:` line: it named
  `provisioning.py` and did not name `deps.py` or `auth.py`, which is backwards
  — provisioning needed no edit at all.

## Final state

125 passed across the five touched modules (from 10 red / 115 green). Whole
suite 2063 passed. `ruff check .` and `ruff format --check .` clean tree-wide;
`mypy` clean over the five changed source files; `alembic check` clean before
and after a round trip. No test file touched, no dispute raised.
