# Entry 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 24**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*18 instances recorded; the 4 below are the most recent, newest first.*

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
genuine catch = **21**; the paragraph that counted as the twenty-first was
E0-33's, which has since been trimmed out of the four shown and is in this file's
git history. The lesson is the one the note was already reaching for: a bump with no
instance paragraph is unfalsifiable a week later, so write the paragraph in the
same change or do not move the number.*

*(E0-28 item 3, and the hazard is **one identifier a platform mints and then has
to recognise.** Every line item id this mock hands out now carries
`?type_id=<ordinal>`, because a bare id lets a tool build its Score URL as
`id + "/scores"` and be right here forever. The dispatch brief spelled the change
as two sentences — `create_line_item` mints
`f"{line_item_url(...)}?type_id={ordinal}"`, and `GradeBook.line_item`
"reconstructs the same string for lookup" — which is literally two copies of one
format string, in one class, thirty lines apart. The half that would have rotted
is not the mint: it is the lookup, which nothing calls until a tool follows an id
the platform gave it, so a divergence surfaces as a 404 on the platform's own URL
in whichever job followed the link. It went in as one method,
`GradeBook.line_item_identifier`, called from both. The same round had the
matching case one layer up and got it for free: `result_url` composes both the
`resultUrl` a score post answers with and the `id` a `Result` gives itself,
because `result_document` calls it — a passback follows the first and a
reconciliation follows the second, and a fix reaching one of them leaves half a
defect wearing a correct-looking URL.)*

*(Building E0-18 PR 1, the two doors themselves, and the hazard is **one URL a
platform compares exactly.** The launch door's `redirect_uri` is
`PUBLIC_BASE_URL` plus the launch path, and the platform checks it character for
character against its registered `MOCK_LMS_TOOL_LAUNCH_URL` — so the path had to be
written in `app/lti/launch.py`, which builds the redirect, *and* in
`app/api/lti.py`, which declares the route it names. Two copies, and the failure
mode of a drift between them is a launch the platform refuses with a message about
an unregistered address, which reads as a broken platform. `LOGIN_PATH` and
`LAUNCH_PATH` are now constants in the module that builds the URL, and the router
declares its routes from them. The same grep found a second one and it was already
written twice by then: both doors assemble a redirect out of a configured endpoint
plus parameters, and both had a copy of "append a query without dropping the one
the endpoint already had". It went into `app/api/deps.py::with_query`, which both
routers call. Neither is subtle; both were about to ship, because the second caller
is what makes the first one look like duplication.)*

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
