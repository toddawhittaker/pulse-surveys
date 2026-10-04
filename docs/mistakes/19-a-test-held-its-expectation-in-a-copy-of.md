# Entry 19. A test held its expectation in a copy of the thing it was checking

**Caught: 10**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*10 caught; this file keeps three instances. Dated from git, the oldest recorded was E0-15's (added 2026-08-18) — dropped in E1's Batch D, then E0-28 and E0-33 (both 2026-08-18) in E5-11, then E3-04 and E1-D on 2026-10-03, leaving E5-11, E5.1-04 and E5.1-03. The paragraphs below are not in date order; cite them by content, not position.*

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

*(**A catch**, writing E5.1-04's tests, 2026-10-03. The rule refuses
`.env.example`'s `SESSION_SECRET` outside development, and the obvious test
holds that placeholder as a literal or imports the constant `app/config.py`
keeps. Either would agree with itself if the template's value changed. The tests
read the placeholder from `.env.example` itself, so the file and the code cannot
drift apart unnoticed.)*

*(**A catch**, writing E5.1-03's tests, 2026-10-03. The door pages and the dev
console now share one design-token CSS block, `DESIGN_TOKENS_CSS`, and the test
checks every value in it against `design/tokens.css` rather than against a copy
of the values held in the test.)*

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
