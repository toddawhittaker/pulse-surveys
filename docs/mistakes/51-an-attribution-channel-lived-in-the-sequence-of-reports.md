# Entry 51. A confidentiality property held in every payload and failed across the sequence of them

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** E4-04's released comments carry no week: SPEC §4 holds a small
week's comments back precisely so that no instructor can tie a comment to the
handful of people who answered that week, and the release batch strips the week
attribution on the way out. Every test of a single report agreed, and the property
is real in any one payload — a released comment names a section and a term and
nothing narrower.

The first release gate fired on cumulative comment volume alone, and a cumulative
count only grows. So the first Monday the term crossed the threshold cut a batch,
and **every later Monday cut another one** — each holding whatever had closed in
the week since. An instructor who reads the report two Mondays running does not
read two payloads; they read the difference between them, and that difference is
one week's comments labelled by the Monday they appeared on. The report itself
re-attached the week the payload had carefully removed.

The security round named it, and the three-Monday sequence test is what made it
visible: run the cutter on three consecutive Mondays over a section with quiet
weeks closing in between, and read the batches rather than the payload. The fix is
the two-week-span leg — a batch is cut only when the unreleased held comments span
at least two distinct under-threshold closed weeks — so the smallest thing a delta
can ever be is one of at least two quiet weeks and one of at least a threshold's
worth of people, which is the candidate set §4 already accepts. ADR 0153 states
the residual and the withholding cost honestly.

**Root cause.** The confidentiality property was specified, implemented and
asserted one payload at a time, and the reader is not a payload — the reader is a
person with a memory who sees the surface every week. Nothing in the suite drove
the surface twice, so no test could see a channel that only exists between two
runs. A release rule that can fire again as soon as anything new arrives converts
each later firing into a difference small enough to attribute, and each of those
firings is individually correct by the rule.

**Consequence.** Caught before merge. Had it shipped, the suppression §4 exists
for would have been defeated by patience alone, with no defect visible in any one
report, nothing in the audit trail to look at, and the released comments
unrecoverable.

**Rule.** A guarantee proven over one response, one report or one export is a
guarantee about one payload. For any surface a person sees repeatedly, ask what the
difference between two consecutive views reveals, and assert the property over the
sequence rather than over a fixed world: drive the surface the way the reader meets
it — this Monday, then the next, then the one after — and read the artifacts the
runs leave behind, not only what each run returns.

The design half: **a gate whose input only grows stays crossed forever.** Once
such a gate has fired, every subsequent firing is about whatever arrived since,
which is the small set the gate existed to avoid disclosing. Either the gate is
re-asked about the *unreleased* set rather than the cumulative one, or it carries a
condition that a single new week cannot satisfy on its own.
