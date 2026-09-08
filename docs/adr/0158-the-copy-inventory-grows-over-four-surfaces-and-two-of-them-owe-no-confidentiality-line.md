# 0158 — The copy inventory grows over four surfaces, and two of them owe no confidentiality line

## Context

SPEC §4.1 items 4 and 5 are asserted over the copy inventory: item 4 sweeps
every collected string for ranking, composite-score and count-of-instructors
language, and item 5 requires confidentiality copy exactly once per surface.
Both items' footnotes say the inventory grows with each UI epic. Until E4-12 it
held one surface, the student survey.

E4 shipped the largest user-facing surface the product has, and shipped it
outside the inventory. Four copy modules — the page shell, the trend pair, the
statistics block, the comment groups — landed in `frontend/src/components/`
rather than in the directory the collector walks, each ticket recording in its
own header that nothing swept its strings. Two more bodies of shipped text were
outside it for longer: SPEC §3.4's gradebook label and per-week ledger line,
written as literals beside the code that posts them, and the fallback screen's
two sentences, written into its JSX.

Growing the inventory over all of that raised three questions the spec does not
answer. How many surfaces is one screen assembled from four files? Which string
is the report's item-5 line? And what does item 5 require of a body of copy that
tells nobody anything about identity?

## Decision

**The report's five prefixes are one surface.** `instructor_report_page`,
`instructor_report_trend`, `instructor_report_stats` and
`instructor_report_comments` from the frontend, and `instructor_report` from the
registry, all map to `report`. Four frontend files exist because four tickets
built four regions; a reader meets one screen. Item 5 counts per surface, so
five surfaces would demand five confidentiality sentences on one page — the
opposite of what the item says. The fifth prefix is the report API's two
refusals, which are the screen's words as much as the other four are; the survey
is the precedent, with `student_survey` from the frontend and `submit` and
`student` from the registry siblings on one surface.

**The report's line is `instructor_report_page.comments_note`**, the standing
sentence under the comment groups saying what an instructor is and is not shown
about who wrote what. The recognizer gains the marker `no names` to see it: every
marker before this one was written from the student's side of the promise, and
this sentence is addressed to the person reading it.

**`instructor_report_comments.small_n.body` is deliberately not recognized.** It
explains why a thin week's comments are withheld — suppression state, present
only in the weeks it applies to. Recognizing it would count a second
confidentiality string on the report in exactly those weeks, so item 5 would
pass or fail by how many students answered.

**A governed surface either carries item 5's line or is recorded as owing none.**
Two maps, and a rule requiring every surface to sit in exactly one of them.
`gradebook` — a course-activity label and an arithmetic ledger, rendered inside
another product — and `unknown_address` — a fallback screen showing nobody's
data — are governed for item 4's vocabulary and owe no line, each with its reason
written beside it. Owing none and carrying none are held to be the same
requirement: a second rule refuses a confidentiality sentence on those surfaces.

**The gradebook is collected rather than excused.** That the surface rendering
those two strings belongs to another product is a fact about rendering, not
about authorship.

## Alternatives rejected

**Four report surfaces, one per copy module.** Mechanically simplest and wrong
in the direction that matters: it would have required four identity promises on
one page, which is the repetition item 5 exists to prevent.

**The small-N body as the report's line.** It reads like the strongest privacy
sentence on the page, which is exactly the trap. A promise that appears only in
some weeks is not a standing promise, and it would make an invariant's verdict
depend on a response count.

**Exempting the gradebook, and recording why it is not a governed surface.** The
ticket allowed this. Rejected because the argument for it is about who draws the
pixels, and items 4 and 5 are about who writes the words. The two strings are
Pulse's, read by an instructor, and nothing else about them differs from a
string on a Pulse screen.

**Inferring a no-line surface from the absence of a row.** A surface somebody
added and stopped halfway through would then be indistinguishable from one
deliberately excused, and the state that arrives by omission would read as a
decision. Two explicit maps plus a totality rule makes placement a choice.

**Reading a no-line surface's item-5 count as unconstrained.** Zero would then
be enforced by nothing, and a reassuring sentence on a gradebook column would
be a second copy of the product's promise that no count could see.

## Consequences

The inventory holds four surfaces and ten prefixes, and every collected string
is swept for item 4's vocabulary — the report's included, which is what E4-12
existed to achieve. The report's copy modules had to move into
`frontend/src/copy/` for that, and moving them cost one thing the ticket did not
anticipate: the copy parser refuses a quotation mark outside a copy file's object
literal, so the statistic module's two number formatters, which name their own
keys, moved out to `frontend/src/components/instructorReportFigures.ts`.

`no names` in the recognizer is a phrase, and any future string containing it on
a line-carrying surface will be counted as that surface's confidentiality copy.
On the report that is enforced as exactly one, so a second such sentence is a
red rather than a drift — which is the intent, and is why the credit-rule note
shipped in this ticket carries no marker at all.

The surface split has to be maintained: every future governed surface is placed
in one of the two maps in the change that adds it, or the totality rule reddens.
That is a small standing cost paid to keep item 5 from quietly stopping at the
edge of whatever was built last.

Two things this does not reach, stated rather than left to be found. Where a
confidentiality line sits on a screen, and how many times it renders, is still
an end-to-end spec's question — this counts strings in an inventory. And a
surface whose strings are assembled at runtime is invisible to all of it.
