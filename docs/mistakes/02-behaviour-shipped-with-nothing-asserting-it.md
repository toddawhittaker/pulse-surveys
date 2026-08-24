# Entry 2. Behaviour shipped with nothing asserting it

**Caught: 33**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*14 instances recorded; the 3 most recent are below, newest first. The earlier 11 are in this file's git history and in the pull requests they cite.*

*(Found while building E0-41 (Batch I, 2026-08-22; that ticket has not merged),
where the subject is read paths the §4.1 invariant suite never touches — the LTI
launch door and the service-layer reveal among them. Every sweep the ticket adds
is written against **the forbidden state rather than the permitted one**, which is
this entry's second sentence applied to a coverage gap rather than to a feature: a
sweep saying "these modules are marked" goes green the day somebody deletes a
module, while a sweep saying "no read path reaches identity unmarked" keeps
working when a legitimate second read path arrives, and fails when an
illegitimate one does. The distinction matters most here because the thing being
asserted is *absence of coverage*, which is the easiest property in the world to
satisfy by accident.)*

*(Batch H item 1, and the shape is **a briefed replacement that would have
un-asserted an older guarantee**. The orchestrator's brief said to replace
`test_db_engine_configuration.py`'s `not engine.echo` assertion with the
captured-log test, because the old assertion keeps passing while every bound
parameter is logged. Replace-as-delete would have shipped E0-04's definition of
done — the engine does not echo SQL outside development — asserted by nothing,
reintroducible by a one-line `echo=True` with the suite green. What shipped
instead: the echo test stays, renamed and demoted in its own docstring to say it
is not the confidentiality guard, and the captured-log test carries the §10
property. The two assert different mutations, so "replace" was the wrong verb
and this entry is what caught it.)*

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
