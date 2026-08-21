# Entry 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 22**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*16 instances recorded; the 3 below are the most recent, newest first.*

*The trim this file asked for has been done, without a shell, by ticket order
rather than by `git log`: the two **E0-16** paragraphs went, because E0-16 precedes
E0-26 and E0-33 in the epic and no reading of the dates puts either of them above
those two. If that is wrong, both are in this file's git history.*

***Re-derived, and 21 is right.** The note that stood here asked whose the
index's 21 was, having found `docs/MISTAKES.md` at **21** while this file read
**20** with three instance paragraphs, and correctly declined to resolve it alone.
The answer: the index bump was the implementer's, in `fcebebe`, and it was
reflexive — this entry's rule is "grep every place that asks the same question and
route them through **one helper**", and E0-26 does the opposite on purpose, because
the `CARE` check is duplicated across the service and both halves of the door by
design (SPEC §8, and `CLAUDE.md`'s carve-out that duplication in
confidentiality-critical paths is the guarantee). Nothing was stopped, so there is
no instance behind it. It has been withdrawn, which leaves 20 + the test round's
genuine catch = **21**, and the fourth paragraph below is what the twenty-first
counts. The lesson is the one the note was already reaching for: a bump with no
instance paragraph is unfalsifiable a week later, so write the paragraph in the
same change or do not move the number.*

*(Writing E0-18's two door suites, before either door existed, and the hazard is
that **two test modules were about to answer the same question twice.** The launch
door and the web door need the same four things — the five landing `data-testid`
values, the clock-winding that produces a signed-but-stale token, the
tamper-that-keeps-the-signature, and the `lti_platform`/`lti_deployment`
registration, because the two-hat person is driven through the launch door from the
web-login module. A copy of the landing testids in each module is the version that
bites: PR 2's Playwright specs address the same five, so a rename would have had
three places to reach and the suite that missed it would go on passing about a view
nobody serves. All four went into `tests/conftest.py` and are reached as fixtures,
which is also the only channel the house rule allows — a test module that imports
its sibling `conftest` by name depends on where pytest put `tests/` on `sys.path`.
The registration in particular was written in the launch module first and moved,
which is the honest version of this entry: the second caller is what makes the
duplication visible, and it arrived twenty minutes later.)*

*(Repairing E0-26 item 1's test round. The suite reported one error —
`ResourceClosedError: This result object does not return rows` — from the `pg_temp`
shadow test, and the cause was a one-line assumption in a shared helper:
`attempt()` called `.mappings().all()` on every result, and `CREATE TEMPORARY
TABLE` returns none. This entry's rule is what turned a one-line fix into the
finding. Grepping the helper's six call sites for the same question — which of
these statements returns no rows? — found two more, the `INSERT` and the `DELETE`
that `test_the_care_connection_cannot_forge_or_suppress_the_record_the_door_writes`
must be refused on. **That test was passing**, and passing for the reason that
makes this expensive: a refused statement raises `DatabaseError` before the rows
are ever asked for, so the bug sat on the branch where the finding is and nowhere
else. Under the exact mutation its own docstring names —
`GRANT INSERT ON public.audit_log TO pulse_care` — the insert would have succeeded,
the helper would have raised `ResourceClosedError`, which is not a `DatabaseError`
and escapes the `except`, and an `invariant`-marked confidentiality test would have
**errored instead of reporting a forgeable audit log**. Fixing only the failure the
runner named would have left that. The check is now in both copies of the helper,
in two modules, rather than in one with a comment in the other.)*

*(Writing E0-33's tests. Its item 3 wants the view *set* compared
with what the migrations wrote, which is the direction
`test_identity_separated_views.py` does not have — it asks whether every view in
the catalog is created by a file under `views_sql/`, and never whether every view
a file creates is in the catalog. Writing that second direction in the new catalog
module meant a second copy of the `CREATE VIEW` regex, and that regex is not
incidental: its word boundary is the subject of an incident under entry 3, where
a sweep for a view's bare *name* was satisfied by the `GRANT` beside it. So the
name extractor was factored out of `creates_view`, which is now one line over it,
the new test went into that module beside it, and the `DROP VIEW` sweep the new
direction needs was added to the same self-test that already runs the create
sweep against what it must catch and what it must allow. **A regex whose
correctness took an incident to establish is the last thing to copy.**)*

**What happened.** In E0-06's test module, `timestamp_columns` discovers timestamp
columns by reflecting from Postgres, and its docstring said why: "a column whose
type is a `TypeDecorator` — the natural place for the criterion 4 guard to live —
is not an instance of `DateTime` and would be missed." The row-seeding helper in
the same file dispatched `isinstance` against the **declared** column type and
got no such accommodation. When the implementation did what the docstring
predicted, both criterion-4 tests died inside the fixture on
`survey_window.closes_at`, before either reached an assertion. It took a dispute
round to settle ([`docs/disputes/E0-06-01.md`](../disputes/E0-06-01.md)).

A second, in E0-09, three tickets later, and it cost another dispute round
([`docs/disputes/E0-09-01.md`](../disputes/E0-09-01.md)). The E0-09 seeding helper
pins two column values so that a freely invented one cannot trip a rule from an
earlier ticket. The section code is drawn fresh per call, because E0-06 made
`(course, term, code)` unique; the course number one line above it was the
constant `"150"`, because SPEC §8 bands the number — and E0-05 also made
`(prefix, number)` unique. So the second course any test seeded under one prefix
was refused, and the three tests that need a sibling lead died inside the fixture
before any assertion ran. The two entries sit in the same dictionary, four lines
apart, and one of them already had the answer.

**Root cause.** Meeting a hazard at the call site where it first bit, instead of
asking which other call sites ask the same question. The write-up made it look
handled: the file named the hazard, in prose, one screen above the code that fell
to it. In the E0-09 case it was narrower still — the two values face *two* rules
each, a format rule and a uniqueness rule, and satisfying the format rule with a
constant is what violates the uniqueness one. Checking the entry against one rule
and stopping is the same shape as checking one call site and stopping.

**Consequence.** Two tests that could not pass against any implementation the
criterion admits, reported as a defect in the implementation. A round of the
loop, and — the expensive shape — an implementer under pressure to satisfy a
fixture rather than a criterion. Two of the four implementations tried in
response would have satisfied the helper *by removing the guard*, and one of them
is what the schema would have shipped.

**Rule.** When you work around a quirk of a type, a parser or an API, grep for
every place that asks the same question and route them through one helper, in the
same change. A docstring explaining the quirk is not a fix for the code that does
not call the fix. And when a test fails inside its own fixture, suspect the
fixture first — the message this one printed said exactly that, and was right.

**A fixture value has to satisfy every rule the column carries, not the one you
pinned it for.** Ask what makes the row *unique* as well as what makes it
well-formed, and prefer a generator over a literal wherever a second row of the
same kind is a shape any test might want. The `"150"` course number still sits in
the private copies of that dictionary in `test_identity_schema.py`,
`test_section_date_derivation.py` and `test_term_calendar_schema.py`; it is
latent there rather than active, because none of them seeds two courses under one
prefix yet.

---
