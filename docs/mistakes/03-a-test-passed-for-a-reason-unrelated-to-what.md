# Entry 3. A test passed for a reason unrelated to what it asserted

**Caught: 39**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*18 instances recorded; the 3 most recent are below. The earlier 15 are in this file's git history and in the pull requests they cite.*

*(Writing E0-34's tests, on a test whose whole subject is a
*failure*. Two of them plant a `.sql` file that reads an identity column and then
assert the guard rejects it, and the natural spelling is
`with pytest.raises(AssertionError):` around the call. That passes for at least
three reasons that are not the one it claims: the guard's own non-vacuity
assertions fire when the planted directory is empty, when the marker convention
has stopped marking anything, or when the redirection of `VIEWS_SQL_DIR` has not
taken effect and the guard is reading the real directory — in each case the
planted file was never swept, and the test reports the guard working. Both now
pin *which* assertion fired by requiring the message to name the identity column
as a whole word, which is the acceptance criterion anyway; the redirection is
asserted before anything is called; and the message that would otherwise be a
puzzle says out loud that a different failure inside the guard is one of the
things being distinguished. The word boundary is the same rule applied once more:
the sibling assertion asks that the *qualification* failure does **not** name the
column, and a substring check answers that wrongly for a column called `name`,
since that message contains the phrase "every relation a view or function
names".)*

*(Writing E0-35's tests, on three sweeps whose subject set is empty today. E0
ships no application write path — the ticket records that as correct — so the
sweep asking which modules write `course` without calling `guard_write` walks the
whole application, finds nothing, and passes; it would pass identically on the
day E1's roster sync lands unrouted in a shape the matcher cannot see. Emptiness
was not the only way the three could have gone green. The marker sweep asserts
that no column on an LMS-owned table is unaccounted for, which is most thoroughly
satisfied by a metadata walk that found no tables; the derived-calendar sweep
asserts that only one module assigns four columns, which is satisfied by a
matcher that recognises no assignment anywhere. So each of the three now carries
both halves of this entry's rule — the samples it must catch and the near-miss it
must allow, one property apart — and a non-vacuity assertion in front of the
emptiness: the marker sweep requires the `lms_` prefix to exist somewhere before
its absence elsewhere is allowed to mean anything, and the calendar sweep
requires the sanctioned writer to be visible to it before its silence about every
other module counts.)*

*(Writing E0-36's tests, twice over. The sweep asking whether a failing gate
reaches the required `CI` check runs the aggregate job's own verdict script under
`bash` and reads a non-zero exit as "the failure was seen" — so a verdict that
exits non-zero for any reason at all, an expression this module substituted
wrongly or a script `bash` could not parse, would report every job as caught and
go on doing so forever. The all-success vector is now executed first and required
to exit 0 before any of the non-zeros count, and an expression the substituter
does not understand fails loudly rather than rendering to an empty string. The
same reading put a non-emptiness guard on both sides of the Docker-gate parity
test, where "the two callers run the same checks" is most perfectly satisfied by
a job that has been renamed and a recipe that was never found; and it made the
`-c requirements.txt` search run against the two spellings it claims to catch and
against the `--output-file=requirements.txt` it must not match, before its
silence about the Makefile is believed. Item 3's round then found the same shape
already merged and green: `test_invariant_gate_is_strict.py` guards its absence
assertion with "the Makefile still invokes the checker at all", and that guard
read the file line by line without cutting shell comments — so the two comment
lines above the `invariants` target, which name `check_invariants.py` while
explaining it, satisfied the guard on their own. Deleting the invocation from the
recipe and leaving the prose would have kept that test green over a `make ci` that
had stopped checking the invariant run. The helper now cuts comments before a line
counts as a command, which is the same rule the two CI-workflow modules already
applied one layer up.)*

**What happened.** A test asserting that a startup error carries no credential
passed against a demonstrably leaking implementation, because ten variables
happened to be set and pydantic's repr elision landed between the two passwords.
Separately, a set-equality test would have passed comparing two empty sets, if
a workflow's shape changed so nothing was collected.

A third, in E0-03, inside the test written to enforce entry 1 below. It asserted
that `ci.yml` no longer carries E0-02's note that "`worker` and `beat` join the
argument list in E0-03", by searching the file text for that phrase. The comment
wraps at 80 columns, so between `join the` and `argument list` the file holds a
newline, six spaces and a `#`. The pattern was written with a plain space. It
matched nothing, and the test went green against the exact comment it existed to
catch — reported as failing, because it had been read rather than run.

A fourth, caught before it landed, and recorded because of where it came from
rather than what it cost. A reviewer's sketch for the E0-06 test holding ADR 0018
ended "assert that afterwards the term still reads N weeks with week N still
present". The refused `UPDATE` runs inside `begin_nested()`, so by the time
anything could query, the savepoint has rolled back and the term reads N whatever
the database did — the assertion cannot fail. It is the same assertion
`tests/integration/test_org_containment_schema.py` deleted for the same reason
during E0-05, proposed again by a careful reader one ticket later. The shape is
attractive because it reads like thoroughness.

A fifth, in E0-08, and it is a shape none of the four above has. The test for
"an enrollment rejects an end date before its start date" wrote a backwards
window and asserted the database refused it. It could not fail. The *other*
criterion in the same ticket is enforced by an exclusion constraint over
`daterange(started_on, ended_on, '[]')`, and Postgres will not construct a range
whose end precedes its start — the error comes from evaluating the expression,
before any constraint is consulted. So the refusal arrived whether or not
anything stated criterion 4's rule, and deleting the check constraint left all
fifteen tests in the module green. Every control that test needed was present and
correct: controls stop a refusal being unrelated to the *row*, and this refusal
was unrelated to the *constraint*. The implementer found it in its own work and
declared it.

A sixth, in E0-10, and it is the first one found by running a mutation the test
itself named. `test_every_read_view_is_created_from_a_sql_file_under_views_sql`
says what it is built against: "move the `CREATE VIEW` into `op.execute("...")`
in a revision file and the sweep below has nothing to read while staying green."
That mutation was performed — `section_roster_v001.sql` deleted, its SQL inlined
into the revision — and all seven tests in the module stayed green. The test
searches the combined text of `views_sql/` for the view's *name*, and
`identity_grants_v001.sql` names both views because it grants on them. So the
sweep is satisfied by a mention and the assertion it advertises is about a
definition.

**Root cause.** Asserting an absence. Absence is satisfied by the thing being
broken in an unrelated way, by a fixture returning nothing, by a parser matching
nothing. In the third case, by the difference between what a sentence looks like
in a file and what it is as a string. In the fifth, by a second mechanism in the
same schema that refuses the same row for its own reasons — "the database said
no" does not say which part of it said so. In the sixth, by a search that matches
the *name* of the thing rather than the thing, in a directory where the name
appears for three unrelated reasons.

**Consequence. ** A green suite is read as coverage. The first case would have
been counted as proof the leak was fixed when it proved nothing about it. The
fifth would have let a later ticket delete a constraint as redundant, with the
rule it states surviving only as a side effect of how overlap happens to be
enforced today. The sixth leaves a layout decision — where a view's SQL lives —
recorded in an ADR and enforced by nothing, which is the state the ADR now says
it is in rather than the state it claimed.

**Rule.** Verify by mutation, not by reading: break the thing and watch the test
fail. Where a test can be satisfied by emptiness, assert non-emptiness first, and
say in the message why that guard is not ceremony. A pattern searched against a
file is a case of this and looks like none: run it against the text you claim it
catches *and* against the text you claim it allows, and give it a canary — a
string certainly present — so a search that has gone blind says so.

**A mutation a test names in its own docstring is a claim, not a record.** Run
it. The sixth case is a test that named the exact edit it exists to catch,
carefully, in the file — and the edit did not catch it. A named mutation is the
cheapest one to try and the one least likely to have been tried.

**Where two rules can refuse the same row, a behavioural test cannot tell you
which one did.** Mutation is what exposes it — delete the constraint and see
whether anything goes red — and the fix is to assert the rule is *stated*, out of
what the catalog reports, as well as that the row is refused. Both, not either:
the catalog test cannot see whether the rule works and the behavioural test
cannot see whether it exists.

---
