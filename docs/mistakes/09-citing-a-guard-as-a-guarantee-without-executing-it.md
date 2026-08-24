# Entry 9. Citing a guard as a guarantee without executing it

**Caught: 18**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*10 instances recorded; the 3 most recent are below. The earlier 7 are in this file's git history and in the pull requests they cite.*

*(**The instance below is not a catch, and the counter does not move.** This entry did not stop it — an independent reviewer measured it, from outside the session that made it. It is recorded because an entry that logs only its successes stops being a measurement.)*

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

*(In E0-17, and it is the entry catching its own half-application.
The `ENVIRONMENT` guard was not cited — it was executed, twice, by hand, and the
results went into ADR 0063 as a table because this entry says a guard you have not
run is a convention. The table was still wrong. It recorded "`ENVIRONMENT` absent"
as covered on the strength of a run that set the variable to the empty string, and
`load_dotenv(override=False)` does not overwrite an empty string — so the case
that was actually asked was "present and blank", and the case the row claimed,
"absent", was never run at all. The test author asked it properly, by removing the
variable, and the guard let the run through. **Executing a guard is only as good
as the case you chose to execute it with, and the cases that differ by one
character — set to nothing, versus not set — are the ones where choosing wrong
looks exactly like choosing right.** The full account is
`docs/disputes/E0-17-01.md`; whether the behaviour or the test is at fault is
still open, and this entry's catch is independent of that ruling.)*

*(In the test that migrates over a stored edge that does not
climb. The plant rests on E0-09's trigger accepting a row E0-11's refuses, so the
same `UPDATE` is attempted at the new revision *first* and required to be refused
before anything is downgraded. A plant that was legal at both revisions would
store the edge, pass every assertion after it, and look identical in the runner —
while proving nothing about a migration.)*
