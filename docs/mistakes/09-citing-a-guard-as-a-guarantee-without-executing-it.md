# Entry 9. Citing a guard as a guarantee without executing it

**Caught: 18**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*10 instances recorded; the 3 most recent are below. The earlier 7 are in this file's git history and in the pull requests they cite.*

*(**Not a catch, and the counter does not move.** This entry did not stop the mistake below — an independent reviewer did, from outside the session that made it. Recording it here because an entry that only ever logs its successes stops being a measurement.)*

*(In the test that migrates over a stored edge that does not
climb. The plant rests on E0-09's trigger accepting a row E0-11's refuses, so the
same `UPDATE` is attempted at the new revision *first* and required to be refused
before anything is downgraded. A plant that was legal at both revisions would
store the edge, pass every assertion after it, and look identical in the runner —
while proving nothing about a migration.)*

*(Inside the helper that plants a non-climbing edge for the cycle
tests. The plant needs the superuser bypass to store a row the rank rule refuses —
and a helper that goes straight to the bypass would keep working on a schema where
the rank rule had been deleted, planting nothing, with the cycle tests still green
and no longer testing what they claim. So it attempts the edge unbypassed first
and requires the refusal before bypassing anything: the guard it depends on is
executed, not assumed.)*

*(In E0-35, and the guarantee was cited in a **brief** rather than in a record,
which is how it reached three records at once. The orchestrator told the test
author that a floor of the spec's three tables would stop the guarded set being
shrunk by an edit to the module under guard. True of those three; stated as
though it covered all four. `user` was in the swept set only through
`authz.LMS_OWNED_TABLES`, so deleting it there left the union answering three
tables and both sweeps narrowed in silence — and the case was never executed,
by anyone, until an independent security review ran it on PR #44 and measured
`('course', 'enrollment', 'section')`. It went red today only in a test of the
adjacent chokepoint, and only because `user` happens to carry an
`lms_`-prefixed column; a guarded table without one had no backstop at all. The
sentence then travelled from the brief into the module docstring, into ADR 0069
and into the pull request body, none of which audited it. The repair is a
direct assertion that the guard's set is a superset of the floor, plus the two
mutations that prove it — delete `user`, and delete `enrollment`, which is the
one with no marked column to save it.)*

**What happened.** Three times. A brief told the test author "a hook denies you
writes elsewhere" — no such hook existed; the hook matched `Read|Grep|Glob` and
denied *reads* of implementation source. Both hooks then turned out to fail open
when `jq` was absent, and one could be bypassed entirely with `cat` through
`Bash`, while their own comments called one "the wall."

The third is the sharpest, and it is a coordination mechanism rather than a hook.
A peer Claude session was asked to run `/clear` before a security review, so the
review would start with fresh eyes. `/clear` is a harness command: nothing a peer
sends can make it fire. The request also carried the line "I know you cannot
report back, because this message goes with it" — which **pre-explained the
silence the failure would produce**. Had the peer simply not replied, that would
have read as confirmation, and the review request would have gone into a context
still holding the previous review and the requester's framing of it. The peer
caught it and said so.

**Root cause.** Reading a mechanism's name and description instead of running it,
then reasoning about what its output would look like instead of observing the
output.

**Consequence.** Two rounds of work proceeded on a guarantee that was not
enforced. The third would have produced a review that looked independent and was
not — *worse than skipping the clear*, because the result would have been trusted
more.

**Rule.** Before citing a guard, execute it against the case you claim it stops
and the case you claim it allows. A guard that has never been run is a comment.
And never write a prediction that explains away the evidence of its own failure:
if you find yourself saying "there will be no confirmation, and that is expected",
you have removed the only signal that would have told you it did not work.

---
