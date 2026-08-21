# Entry 3. A test passed for a reason unrelated to what it asserted

**Caught: 46**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*25 instances recorded; the 3 below are the most recent, newest first. The
earlier 22 are in this file's git history and in the pull requests they cite.*

*The trim the last reader asked for has been done, from git rather than from the
page order, and the warning was worth writing down: the two E0-36 paragraphs
were **not** in chronological order, so cutting from the bottom would have kept
the older of the two. Dating a paragraph is `git log -S"its first phrase"` on
this file.*

*(Writing E0-18's door tests, before any door existed, and it is the shape where
**the only obvious way to pose a case breaks something else at the same time.**
The launch and web doors both have to refuse a token whose `exp` has passed, and
the natural test edits `exp` in the payload and re-encodes it — which invalidates
the signature. That test is refused by a tool that checks nothing but the
signature, and by a tool that checks nothing at all if the decoder trips first, so
it would have gone green over an implementation with no expiry check in it. What
stands instead winds `time.time` back for the length of the mint, so the mock
issues a token that is genuinely expired and genuinely signed, and beside it a
near miss that winds the clock back thirty seconds and requires the launch to be
**accepted** — without which the refusal is evidence that winding the clock breaks
a launch rather than evidence that anything reads `exp`. The same shape decided
three other things in the same batch: the wrong-`aud` and unknown-`deployment_id`
cases move the registration rather than the token, so each refusal differs from
the happy path in exactly one value; the `/docs` gate's closed direction carries a
`/healthz` control, because "both routes answer 404" is also true of an
application serving nothing; and the two empty-landing-page tests assert the
landing testid is present before reporting that no other person's address is on
it, with the scan shown finding those addresses in a sample built out of them.)*

*(E0-30's second fix round, and it is the shape where **the assertion names the
defect instead of the rule**. The first draft for the reflected-`error_description`
finding asserted that the offending bytes were *absent from* the description — which
passes against a provider that deletes the description entirely, against one that
drops the parameter altogether, and against any rewording of a message the fix is
free to rewrite, so it would have pinned prose and guaranteed nothing. What stands
instead is RFC 6749 Appendix A.8's grammar transcribed as a character-set bound,
with the `1*` half of `1*NQSCHAR` asserted separately as non-emptiness: the
production rather than a guess at the fix, and the reason three raise sites are
driven rather than the one the reproduction named. The registration half of the same
round is this entry's other face. `pytest.raises(Exception, match=...)` is satisfied
by any exception whose message matches, so "it refused" and "it refused for this
reason" are separate claims — and the only thing separating them is the accepted-query
control beside the new cases, a registered `?tenant=x` that must still register.
Without it, both new cases pass perfectly against a rule that had become "refuse
every query", which is a different and worse provider.)*

*(Writing E0-30's error-redirect battery, and it is the shape where **the
obvious assertion is satisfied by three different wrong providers at once**.
"The refusal is a 3xx to the registered URI carrying `error`" passes against a
provider that hands back an authorization code beside the error, against one
that answers a single constant code for every refusal, and against one that
re-encodes the `state` a client will compare byte for byte. So the helper every
redirect case goes through refuses a `code` in the returned query, requires
`error` to be one of RFC 6749 §4.1.2.1's codes **and** each test to say which,
and requires `error_description` to carry something. The page assertions were
worse, and worse in exactly the way this entry is named for: "this refusal did
not redirect" was a true statement about the provider as it stood, which
redirected nothing at all — all eight page cases passed on the day the ticket
opened and would have gone on passing over an implementation that never changed.
The ordering near miss, which is the one that guards against an open redirector,
now asserts both halves in one run: the same unknown scope with the registered
redirect URI must redirect, and with an unregistered one must not, so the
negative half is only read once the positive half has been seen.)*

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
string certainly present — so a search that has gone blind says so. **Build that
canary sample by copying whole lines, the line the sentence starts on included.**
A sentence retyped from where you think it begins is the thing the sample exists
to disprove, and a comment wrap is exactly what puts the boundary somewhere you
did not expect.

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
