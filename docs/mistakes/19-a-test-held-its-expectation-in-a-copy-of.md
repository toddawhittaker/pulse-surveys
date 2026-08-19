# Entry 19. A test held its expectation in a copy of the thing it was checking

**Caught: 4**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*4 instances recorded; the 3 most recent are below. The earliest is in this file's git history and in the pull request it cites.*

*(In E0-15's tests, over SPEC §8's course-number bands. The mock's seeded
numbers are checked against a transcription of the table, because §8 states the rule
as a markdown table *plus* a sentence of prose about width — three digits only in
`000`–`799`, four only in `8000`–`9999` — and nothing in the repository holds that in
a form a test can read. So this entry's escape clause applies and its condition is
met: the comment says the constants are deliberately not derived and why, and a
control test walks every edge the table names, including `2150` from the `design/`
corpus the ticket warns about. Without the control the transcription is a second copy
of the rule with nobody comparing it to the first.)*

*(In E0-11's tests, and it changed where three constants were read
from. The role ranks that decide which supervision edges are legal are written
out of SPEC §2.1's canonical chain rather than read back out of the trigger under
test — the only other copy of that order is inside the guard, so a test that
queried it would let both be renumbered together while staying green. The
LMS-owned table list is §2.1's ownership sentence rather than a copy of the
module's own `LMS_OWNED_TABLES`, which is the constant it exists to check. The
n-threshold default is §4's "default 5" rather than whatever `Settings` answers,
so a configuration defect and a resolver defect fail as two different
assertions. The `Purview` field list is transcribed from the ticket and says so,
because reading it off the dataclass would admit a seventh field silently — this
entry's rule for a value that genuinely has to be written into the test.)*

*(In E0-33, deciding where "exactly what the migrations wrote" is
**written**. The hand-written set of what the two connection roles may hold on a
base table went red on its first run, against a legitimate grant it did not know
about — E0-13 grants `pulse_app` `SELECT, INSERT` on `classification` — which is
two lists in two places with nothing comparing them, and the obvious repair is to
stop hand-writing it and read the `GRANT` statements out of
`backend/app/views_sql/*.sql` at run time. That repair is this entry: those files
are the thing the test polices, so every grant would justify itself — the file
says grant it, the catalog says granted, the test says fine — and a later ticket's
convenience grant, which is exactly a line added to one of them, would be green.
The set stays hand-written, each entry now carries the sentence it is derived from
(SPEC §8's "`classification` is append-only" for the two new ones), and the
failure message carries four questions for telling a legitimate grant from a
widening. **A red on a legitimate change is the price of an exact set; a green on
a widening is what the derived version costs, and only one of those is loud.**)*

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
