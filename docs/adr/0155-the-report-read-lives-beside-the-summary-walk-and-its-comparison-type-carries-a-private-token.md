# 0155 — The report read lives beside the summary walk, its refusal pair is one 404, and its comparison type carries a private token

## Context

E4-07 ships the first instructor-facing read in the product: the Monday report
for one section and one course week, and the list of published weeks navigation
pages across. Its ticket leaves five construction questions open, and each of
them is one a reasonable engineer would settle the other way.

**Where the read service goes.** The ticket asks for "a new module under
`backend/app/services/` whose ADR says why no existing module fits". That
instruction was written before E4-06 merged. `app/services/reporting.py` now
exists, its own module header claims E4-07's read side explicitly, and SPEC §13
names `reporting` for "distributions, trend lines, benchmark assembly" — which is
this read and nothing else. So the open question is the reverse of the one the
ticket asked, and it has to be answered rather than assumed.

**Where E9 attaches.** SPEC §5.5 renders this same report read-only inside a
leadership shell, and E4's breakdown puts every leadership and purview read in
E9. Whether E9 extends this payload or builds its own decides whether §4's
suppression rules have one implementation or two.

**What a refusal says.** A section the requesting instructor does not teach, and
a section that does not exist, need an answer each. The ticket recommends 404 for
both and leaves the mechanism open.

**How SPEC §4.1 item 7's chokepoint is made unavoidable.** The ticket asks for it
to be "proven structurally (the member's type is private to the helper's module,
or an equivalent the ADR defends)". E4 computes no comparison set at all, so
whatever is built has to survive E5 being written by somebody who never read this
ticket.

**What a rate does when its denominator is zero.** ADR 0147 moved every division
out of SQL and into this layer precisely so the rule would be written once, and
then did not write it. E4-07's criterion 7 says a zero-response published week
"returns the full shape — zero rates, empty distributions, the week in
navigation", which reads as "everything is zero" and cannot be.

**And where the released comments go.** ADR 0152 says E4-07 places them and names
the week; it does not say what happens in the other weeks' reports.

## Decision

**The read lives in `app/services/reporting.py`, beside the summary walk, and no
new module is made.** The module docstring now names both halves and the line
between them. Two things share these rows — the walk that writes a week's
summaries and the read that renders them — and a second module would have SPEC
§13's one name for §5.1 split across two files with no rule saying which is which.

**E9 attaches at `_readable_section` and nowhere else.** Every other function
below it takes a `Section` row that has already been established as readable, so
E9's drill-down adds a purview-based route to that one function and inherits the
whole payload, its suppression and its zero-fill. This is written into the module
header as well as here, because the failure it prevents is a later ticket forking
`instructor_report` for a shell that renders it differently.

**Both halves of the refusal pair are 404 with one sentence, produced by one code
path.** Scope is decided by a single question — does this person hold the
`INSTRUCTOR` grant over this section — asked through `app.services.authz`, which
is SPEC §13's authorization chokepoint and the only module that reads
`assignment_scope`. A section that does not exist has no such row for anybody, so
it fails the same test at the same line: there is no existence check to time, no
second body to compare, and no branch that could drift apart. The sentence names
nothing it was handed.

**A wrong-role session is refused 401 with a `Bearer` challenge instead**, in
`app.api.deps.require_instructor`, and the difference between the two statuses is
load-bearing rather than incidental: a leadership session answered 404 would mean
the role gate had let it through and the scope query had refused it, which is E9's
shape arriving three epics early.

**A report is served only for a published course week, and the week is selected
out of the published set.** SPEC §3.1 puts the report after the window closes and
this ticket's Context asks for one published course week; a week still taking
responses is refused with byte-for-byte the refusal a week the section never runs
receives. The first version of this record rejected that rule and shipped the
defect — see the reversed paragraph under *Alternatives rejected*, which is kept
in full because its reasoning is the thing to recognise next time.

**Item 7's chokepoint is a module-private construction token, checked again at the
wire.** The `comparison` member's type, `ComparisonFigure`, lives in
`app/services/reporting.py` and its constructor demands a module-level object that
nothing outside that file can reach. `app/schemas/report.py` types the member with
it.

The constructor alone turned out not to be a chokepoint, and this record's own
security round is what found it: pydantic produces instances two documented ways
that never call `__init__` — `model_construct`, which runs neither validation nor
initialisation, and `model_copy(update=...)`, which rewrites the fields of a value
the helper had already suppressed. Both were demonstrated ending in a serialized
payload carrying a figure §5.1 means to suppress. So **the boundary is the wire**:
`ComparisonFigure` records a private seal over its own field values at the moment
the token is accepted, and `InstructorReport`'s `mode="after"` validation of the
`comparison` member refuses any value whose seal does not match its fields. The
first door produces an instance with no seal at all; the second produces one whose
seal is over the values it held *before* the update. A seal that merely recorded
"a token was seen" would pass the second, because `model_copy` copies private
attributes too — which is why the seal binds values rather than recording an event.

The helper is still the only thing that can build one, and it reads *both*
configured minimums —
`benchmark_min_sections_default` and `benchmark_min_respondents_default`. The
report itself goes through it: E4 has no comparison set, so it asks for a figure
of nothing over no sections and no respondents and carries back the suppressed
value. E5 calls the same function with real numbers.

**The zero-denominator rule, written out.** A rate whose denominator is zero has
no value, and its absence is a member holding null rather than a member that is
gone. With an enrolment above zero and no responses, `response_rate` is `0.0` — a
real fact about a real week. With no responses, `validity_rate` is absent, because
`0.0` would say every response that week was invalid and there were none. With no
enrolment, `response_rate` is absent the same way. Criterion 7's "zero rates" is
read as: rates that have a value are zero, and the ones that have none say so.
The same rule makes a quiet week's distribution five zeros — nobody chose any
value, which is true — while its trend point carries no mean at all, because zero
is outside SPEC §3.2's scale and would plot below every real point.

**The released list is a member of every report and is populated in exactly one.**
`released_from_earlier_weeks` is present as a list in every payload and filled
only when the requested course week is the latest published one, per ADR 0152. It
carries `ReportComment`'s own three fields and no week, per ADR 0153. Present
everywhere so the frontend has one shape to render; filled once so that a reader
paging back through the term does not meet the same batch beside six different
weeks of data — which is the week attribution ADR 0153 removed, arriving through
the navigation instead of through a field.

**The enrolled denominator is overlap with the week's window**, computed here and
not in SQL (ADR 0147). An enrolment counts if it had begun by the day the window
closed and had not ended before the day it opened, in the institution's own
timezone, with section staff excluded the way `app.services.grading` excludes
them from a participation score.

## Alternatives rejected

**A new module for the read, as the ticket's own scope line asks.** Rejected
because the fact it was written against changed: E4-06 merged first and its
header already claims this read. Two modules would need a rule for which of them
owns a number, and the first candidate — "the writer owns what it stores, the
reader owns what it divides" — puts `weekly_summary` on both sides of the line.

**403 for out of scope and 404 for absent**, which is what an implementation
reaches for when it validates the parameter first and consults the session
second. Rejected outright: the difference answers "does this section exist" for
any signed-in instructor, one request at a time, over every id in the
institution. A shared 404 with two sentences was rejected for the same reason one
layer in.

**The comparison type defined in `app/schemas/report.py`, "so the schema owns its
own types".** This is the tidying that removes the whole mechanism: a token
private to the schema module is reachable by anybody who can import the schema,
which is every caller the chokepoint exists to stop. The cost of keeping the type
in the service is a cycle between the two modules, and it is paid with one
function-local import in `_payload`, named and explained there.

**A convention instead of a token — "the helper is the only supported way to
populate this member".** Rejected on `docs/MISTAKES.md` entry 22: a closed-set
guard is defeated one level out, and a rule that every future caller must
remember is exactly that. E5's benchmark assembly, E9's drill-down and any later
export are each an opportunity to build a comparison value some other way, and
none of them will be reviewed by somebody holding this ticket in mind.

**`validity_rate` of `0.0` for a week with no responses**, which satisfies a
plain reading of "zero rates" and is one character cheaper. Rejected because it
is a false statement to an instructor: it says every response that week was
invalid, in a week that had none, and §3.3's rate is one of the two numbers §5.1
puts at the top of the page.

**~~Refusing a report for a week whose window has not closed.~~ Reversed by this
record's own security round; the original paragraph is kept because its reasoning
is what shipped the defect.** It read:

> Tempting, since navigation lists only the closed weeks. Rejected as a rule
> nothing asks for: a report for an open week is a true report of what has arrived
> so far, and refusing it would be this module inventing a state the spec does not
> have. What is refused is a course week the section has no window for at all.

**Every clause of that is wrong, and two of them were checkable against documents
this record cites.** SPEC §3.1 makes the report available after the window closes,
and E4-07's own Context asks for "one **published** course week" — so the rule was
asked for, twice, and this paragraph rejected it as unasked. It is not this module
inventing a state either: published-versus-open is E4's breakdown decision 6, and
the same function already computed the set two lines above the place it then
ignored it. And "a true report of what has arrived so far" is the substantive
error: a report is true of an instant, and an instructor who reads one twice is
subtracting rather than reading — the difference between two views of an open week
is one student's submission, arriving in a week whose whole small-N apparatus
exists to keep exactly that inference out. `docs/MISTAKES.md` entry 51 names the
shape; this paragraph is a fresh instance of it, written by somebody who had read
that entry.

**What is decided now:** the report is served only for a course week in the
published set, and the refusal for an open week is byte-for-byte the one a week
the section never runs receives — same status, same body, selected out of the
published list rather than tested against it, so there is one code path and
nothing to tell "not yet" from "never". Telling those apart would hand back the
section's calendar a week at a time.

**Carrying the released list in every week's report.** Simpler, one branch fewer,
and it re-attaches the week for free — the batch that was not there last Monday
came from the week that closed in between. Rejected on ADR 0153's argument.

**Computing the enrolled denominator in SQL**, or reusing "enrolled today".
Rejected by ADR 0147 already for the first; the second is rejected here because a
report is about a week in the past and a count of the enrolments live *now*
answers week two and week five with the same wrong number. A narrower per-week
rule — enrolled on the day the window closed — was also rejected: a student who
answered on the Monday and dropped on the Tuesday would be in the numerator and
not the denominator, and a response rate above 1 is a report nobody can read.

## Consequences

- **One module holds §5.1's read and its write.** It is longer than either half
  would be, and a reader has to know the line between them; the header names it.
- **`app/schemas/report.py` imports `app/services/reporting.py`, and the service
  imports the schema back inside one function.** That is a real cycle, paid
  deliberately for the token's privacy, and it is the one function-local import in
  the module. Anyone tempted to lift it to module scope will break the import.
- **E5 cannot ship a comparison figure without going through the suppression
  helper**, because there is no other way to build a value the payload boundary
  admits. If E5 needs a shape this type does not have, the change is to this type
  and its helper — which is the review that ticket should get.
- **The seal costs every report one tuple comparison and costs a reader an
  indirection.** `ComparisonFigure._sealed_over` is a private attribute nothing
  serializes, `_the_seal_over` builds the tuple from `model_fields`, and
  `refuse_an_unsealed_comparison` is the only reader. The failure mode to know
  about: anything that produces a `ComparisonFigure` carrying a figure without
  going through the helper now raises a `ValidationError` at the payload boundary
  rather than serializing quietly, which is deliberate — reaching there at all is a
  defect in a confidentiality path, not a state to render.
- **The seal enumerates fields automatically and holds them by reference, which
  are two different guarantees.** A field added to the type is enumerated by the
  seal by existing; it is only *bound* by it because every field this type has is
  immutable, so a value cannot change without the tuple ceasing to match. A mutable
  field added later — a list of contributing sections, say — would be the same
  object after being mutated in place, so the seal would still compare equal and a
  figure could be written into it after the token was accepted. Adding a mutable
  field means `_the_seal_over` has to copy rather than reference, and nothing
  enforces that today beyond this sentence and the one in that function.
- **The `comparison` member is re-checked on every report even though E4 computes
  no comparison set, and `InstructorReport` re-validates itself on every response.**
  `revalidate_instances="always"` is the outermost of the three layers and the last
  one the review found: a field validator runs when a model is *validated*, and
  `model_construct` and `model_copy(update=...)` build a report that no validator
  sees, which the re-pass demonstrated serving an unsuppressed figure with a 200.
  The cost is a second validation pass per report, paid on every request, and it is
  what makes the guarantee about what is shown rather than about how somebody built
  the thing shown.
- **An unsealed comparison member is admitted in exactly one shape: suppressed,
  with no figure.** That is what lets the payload be validated from its own
  serialized JSON — pydantic builds a model with a custom `__init__` *through* that
  `__init__`, so a round trip arrives with no token and therefore no seal, and
  every E4 report's comparison member is that shape. It gives up nothing item 7
  asks for: a member saying "no comparison here" discloses no figure whoever built
  it. Anything carrying a figure, or claiming it was not suppressed, still has to
  be sealed.
- **SPEC §4's n-threshold is read through one function,
  `app.services.report_comments.n_threshold`, rather than passed down as a
  `Settings`.** The report *prints* the threshold in its `small_n` member beside
  the comments the gate hid, and the security round found the two reading it
  separately — the label from the application's startup configuration, the gate
  from a fresh `Settings()` per call — which is a screen describing a rule the
  query did not follow. Passing the report's own `Settings` into
  `visible_comments` is the plainer fix and is not available: E4-04's work order
  settles that read's signature at four parameters and an invariant-marked test
  asserts it as an equality, so that no fifth parameter of any kind can be added
  and later filled with something that names a person. That rule is worth more
  than the ergonomics, so the single source is a function both sides call. The
  cost is that a caller holding a `Settings` still may not use it for this one
  number, which reads as inconsistent until you know why.
- **The report and the week list cannot disagree about which weeks are
  published**, because both derive it from `_section_weeks` and the clock service.
- **The instructor report's two refusal sentences are outside `app.copy`.** E2-11's
  inventory governs a key by its surface prefix and the report is not a governed
  surface yet, so a copy module under a new prefix would red that inventory.
  `docs/tickets/e4/deferred.md` carries the entry, owned by E4-12 with the rest of
  the report surface's copy. **Amended 2026-09-08 by E4-12**: the report is a
  governed surface now ([0158](0158-the-copy-inventory-grows-over-four-surfaces-and-two-of-them-owe-no-confidentiality-line.md)),
  so the reason above has expired — but the two sentences are still literals in
  `app.api.instructor` and still collected by nothing, because placing them needs
  a row in the inventory's governance map and that map is behind the test wall.
  What stays true is the state, not the argument for it; the residue is open and
  unowned rather than closed.
- **The course label is composed twice** — here and in
  `app.services.survey_read._course_label`, which E4-07 was scoped not to touch.
  The pull request proposes promoting one shared helper; until that lands the two
  are edited together or a student's page and her instructor's report name the same
  course differently.
