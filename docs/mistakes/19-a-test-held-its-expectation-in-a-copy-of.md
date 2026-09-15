# Entry 19. A test held its expectation in a copy of the thing it was checking

**Caught: 8**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*8 caught; this file keeps three instances. Dated from git, the oldest recorded was E0-15's (added 2026-08-18) — dropped in E1's Batch D, then E0-28 and E0-33 (both 2026-08-18) in E5-11, leaving E3-04, E1-D and E5-11. The paragraphs below are not in date order; cite them by content, not position.*

*(**A catch**, writing E5-11's round 2, 2026-09-14, twice in one e2e file. The
DOM sweep needs a figure to search the student's screen for, and the obvious
source is the arithmetic the seeder's docstring gives for the hero's comparison
mean — a number typed into the spec that would agree with itself whatever the
page showed. It is read off the hero report's own payload instead, in the spec,
guarded non-integral before it is searched for, and required to appear in the
instructor's DOM before the student's is judged clean. The second: the canary's
vocabulary is transcribed from the copy files with a comment naming each source,
not imported from them, so a legend respelled in `instructorReportTrendCopy.ts`
reds the canary instead of moving the expectation with it. The backend needle
test was widened on the same rule — four figures, each taken off the served
report, none computed in the test.)*

*(**A catch**, writing E3-04's tests, 2026-09-04, in two places that look
different and are the same. The first: the enforcement module's whole subject is
which scope opens which AGS route, and `mock-lms/app/ags.py` declares all four as
constants — importing them would put the route map and the assertion about the
route map in one blast radius, so a scope respelled in the mock would move both
and stay green. They are transcribed from the IMS specifications with a comment
saying they deliberately are not derived, and the mock's own `ADVERTISED_SCOPES`
is then read *through the platform's discovery document* — which is where a tool
finds them — rather than imported, so the two copies are held against each other
by the platform at run time. The second is the score maximum: criterion 4 says
the client posts "the line item's own maximum", and the assertion reads that
maximum back from the platform's line-item document rather than from the number
this suite seeded with, so a client that echoed a constant is caught by the
platform's own refusal rather than by a literal agreeing with itself. The same
reading is why the ledger and the percentage in `tests/fixtures/ags_client.py`
are values a caller hands over and nothing in that file derives: a fixture that
computed either would be a second implementation for criterion 3's comparison to
agree with, and the comparison is the criterion.)*

*(Writing E1's cleanup Batch D — the security response headers — over
`frame-ancestors`. The directive must be `'self'` plus the origin of every
registered platform's `authorization_endpoint`, and the repository already has the
function that computes exactly that set: `launcher_origins`, which the developer
console uses and which the middleware is required to reuse. The obvious way to
write the expectation is to import it and compare the header against what it
returns, and that import is this entry. The middleware and the test would then be
reading one function, so a `launcher_origins` mutated to return an empty list, the
wrong column, or a hardcoded address would move both sides together and stay
green — the whole derivation could break with the suite reporting nothing. Every
expected origin in `tests/integration/test_the_security_response_headers.py` is
instead computed from the endpoint **the test itself registered**, with the
stdlib-only `origin_of`; nothing from `backend/app/` is imported at all. The
`admits_any_origin` and policy-parser controls are what keep the independent
expectation from being independently wrong.)*

**What happened.** E0-12's moderation contract test asserted that the verdict
enum offers exactly the six values SPEC §7.4's table names. The six lived in a
tuple at the top of the test file, hand-copied from the spec, and the assertion
was a generic helper driven by whichever tuple it was handed. So the test did not
have to be defeated to lose a verdict: deleting `SELF_HARM` from the enum *and*
from the tuple left all 169 unit tests green. An eval-gate review found it by
doing exactly that.

The same file taught the edit. Every discovery constant in it carries a comment
saying it is this suite's choice and that a rename is "the one line that
changes", which is right for the constants that guess at class and field names
and wrong for the one that holds the spec's own words — and nothing distinguished
them.

**Root cause.** Two copies of one fact, both inside the blast radius of a single
change. A test that reads its expectation from a file the change also edits is
checking the code against itself. It is not entry 3 — the assertion ran, and
compared what it said it compared — and not entry 2, because the behaviour *was*
asserted. What failed is the independence of the expectation.

**Consequence.** As caught, none. Unrecognised, the merge of threat and self-harm
into one verdict would have passed CI with a diff that reads as tidying: one enum
member and one tuple entry. §6.2's Care queue distinguishes threat-of-harm from
self-harm risk, and §9.3 makes threat and self-harm recall the strictest floor in
the suite — a floor measured over a merged label is measuring something the spec
does not have, while reporting a number that looks like compliance.

**Rule.** When a test asserts that code matches a document, read the document.
`docs/SPEC.md` is parseable and is the authority; a constant beside the test is
neither. Where a value genuinely has to be written into the test — a count, a
pair of names that a second assertion exists to protect — say in the comment that
it is deliberately *not* derived and why, so the next reader can tell it apart
from a fixture that is free to move. And give a distinction that safety rests on
its own named test: a fold that fails a set comparison reads as a fixture needing
an update, while a fold that fails
`test_the_moderation_contract_keeps_threat_and_self_harm_as_two_distinct_verdicts`
says what was lost in the line the runner prints.

---
