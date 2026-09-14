# 0169 — A withheld comparison statistic is a sentence in the column

## Context

SPEC §5.1 asks the Monday report for the section's workload mean and median
"against comparison-set and university figures", and §4.1 item 7 suppresses
every figure computed from a comparison set below the benchmark minimums — "a
mean, a median, or any other statistic, not only a drawn line". So the workload
pair has two columns that can each be missing, independently, for two different
reasons, in a place where every other cell holds a number of hours.

E4-09 settled how this surface writes a figure it does not have: an em dash,
never a zero, because "0.0" in an hours column reads as "this course took
nobody any time". That treatment was decided for the *section's* own figures,
where the fact behind the dash is "nobody answered this week" and a note under
the pair says exactly that. A comparison figure is missing for a different
reason and the note under the pair does not speak for it, so the treatment does
not carry over untouched. SPEC and the design brief are both silent here: the
prototype draws a single "vs 5.0 h comparable · 4.8 h university" line and has
no suppressed state at all.

## Decision

**A comparison column that has no figure to show says so in words, in the cell,
and shows nothing number-shaped.** The cell holds "Not shown" followed by a
short sentence giving the reason. No dash, no digit, no unit.

**The two reasons are two sentences, because they are two facts.** A suppressed
member (§4.1 item 7) says the set behind the figure is too small to report on —
the second sentence of `instructor_report_trend.comparison_suppressed`, naming
no minimum and publishing no count, for the reasons recorded there. An
unsuppressed member carrying no number says there is no figure for this week,
which is the trend chart's `mean: null` week in the workload pair's shape. A
component that said "too small" for both would state something untrue about the
set every time the second case arrived.

**The reason is on the screen, not only in the accessible text.** A sighted
reader is owed the reason as much as a reader hearing it, and one sentence
serves both.

**Each figure carries a complete label of its own** — "Mean hours, comparable
courses" — rather than sitting under a column header. The pair is a description
list: a label bound to its value in the markup is what makes "Mean hours,
comparable courses: 9.0 h" one fact when it is read aloud, and a header row
would leave each value bound to nothing.

## Alternatives rejected

**The em dash, as for the section's own figures.** It costs the reader the
reason, and in a column of hours it reads as "no hours" rather than as "not
shown" — which is the ticket's named trap. A dash also cannot tell the two
withholding cases apart.

**One withholding sentence for both cases.** Cheaper by one string, and wrong
in one of the two cases: it would assert the comparison set is too small on
weeks when it is not.

**A visually hidden sentence with a dash on screen.** Keeps the prototype's
shape, and gives a sighted reader less than a screen-reader user — the inverse
of what an accessible alternative is for.

**Column headers instead of per-figure labels.** Half as many strings and a
tidier grid, at the cost of the label-to-value binding the list is chosen for;
it also puts the figure's identity and its column in two places that a later
layout change can separate.

## Consequences

Six strings rather than two in `instructorReportStatCopy.ts`, all collected by
the copy inventory and swept under §4.1 item 4. A withheld column is visibly
wordier than a figure, which is the intended reading: something is missing and
here is why.

The component now distinguishes suppressed from empty, so a payload that sends
`suppressed: false` with no numbers gets the honest sentence rather than a
suppression notice. It still fails closed on the flag itself: anything that is
not literally `false` is withheld as suppressed, so a slip in the payload shows
the confidentiality sentence rather than a figure.

E5-10, which joins the real payload, inherits both sentences and needs no
decision of its own; a later surface that renders comparison statistics
elsewhere has a settled treatment to copy.
