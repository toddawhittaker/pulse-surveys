# Entry 2. Behaviour shipped with nothing asserting it

**Caught: 31**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*12 instances recorded; the 3 most recent are below. The earlier 9 are in this file's git history and in the pull requests they cite.*

*(E0-18 PR 1's second round, and it is the shape where **the unasserted behaviour
is the premise of an exception**. The claim-to-Care sweep gained a named exception
for `backend/app/services/landing.py`, and the whole exception rests on one
factual claim: the landing seam chooses a screen and writes nothing. Left as a
sentence in the exception's reason string, that claim is exactly what this entry
is about — true on the day it was written, unguarded afterwards, and load-bearing
for the ticket that ruled the collision. So the reason string cites a test rather
than arguing, and the test drives the whole web login as the Care person and
requires `role_assignment` to be unmoved. The rule's second sentence decided the
shape: the assertion is on the forbidden state, so it keeps working when E1's
legitimate provisioning arrives — and the `user` and `person` half says in its
own message that E1 moves it deliberately, in E1's pull request, rather than
quietly.)*

*(Writing E0-36's tests, on the migration-drift job's two-role shape. The
criterion is that repointing that job's `DATABASE_URL` at the superuser fails
something, and the natural assertion is the permitted state: the connection names
the role the job provisioned, read out of the job's own `DB_APP_USER` so that
renaming the CI role stays a one-place edit. That assertion is defeated by a
two-line mutation — set `DB_APP_USER: postgres` and point the URL at it — which is
the repointing this criterion names, wearing the value the test compares against.
This entry's second sentence is the one that applies, so the **forbidden** state
is asserted beside the permitted one, out of `DB_SUPERUSER` and the Postgres
service's own `POSTGRES_USER`, and each message says which mutation its half
exists for. The same reading is why the provisioning assertion checks the order
as well as the presence: a role created after `alembic upgrade head` is a role the
migration never used, and the step is still sitting there for a reviewer to see.)*

*(In E0-17, and the interesting part is the delay. The
`ENVIRONMENT` guard on `scripts/seed.py` shipped with nothing in the suite
executing it — the module's one run with a deployment name sat behind a condition
that is false — and the implementer noticed, said so in ADR 0063's own
consequences and in the pull request, and shipped anyway because it may not write
under `tests/`. That is this entry working as far as it can reach: **the
behaviour was still unasserted, and what the entry bought was that nobody had to
discover it.** The test author then wrote ten tests against the record's
description, and the tenth failed — the guard is satisfied by `.env` when the
process environment does not supply the variable, which no hand measurement had
asked. So: an entry that turns "shipped unasserted" into "shipped unasserted, in
writing, with an owner" is worth its counter even when it cannot stop the ship,
because the sentence in the record is what got the tests written and the tests
are what found the defect.)*

**What happened.** Four times. `__repr_args__` was added to keep credentials out
of `repr(settings)` — deleting it left the suite green. The `institution_timezone`
validator could be deleted whole with the suite green. "`DATABASE_URL` must never
point at the superuser" was prose, and repointing it passed all 50 tests and the
`docker` gate. The two Postgres image digests could be set to different values
with every gate green.

**Root cause.** Fixing the defect and stopping there. The fix is visible in the
diff, so it feels done; nothing makes the absence of a guard visible.

**Consequence.** The next person deletes it during an unrelated refactor and
every gate stays green. For the superuser case, the exact defect the pull request
existed to fix was reintroducible without any signal.

**Rule.** After fixing something, try to reintroduce it. If the suite stays
green, you have written a convention, not a guarantee. Prefer asserting the
*forbidden* state over the permitted one — it keeps working when a legitimate
second case arrives.

---
