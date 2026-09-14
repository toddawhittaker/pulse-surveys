# E5 — deferred

What an E5 ticket chose not to fix while it was in the file, with an owner and
the condition that closes it. A PR that defers something adds it here in the same
PR; E5-14 runs the cleanup pass over this file at the epic exit.

A deferral is a decision, not a note. Each entry says what is not enforced, why
it was left, who owns it, and what "done" means — a gap recorded only as a
comment in the file that works around it is `docs/MISTAKES.md` entry 48.

## The design brief still maps the two comparison lines to a colour that fails the contrast floor

**What is not enforced.** `docs/DESIGN_BRIEF.md`'s chart mapping reads
"Benchmark = mist, dashed. University = mist at 50%, dotted", and
`design/PulseTrendChart.dc.html:17-18` draws exactly that. E5-07 ships those two
lines in `--spruce-60` instead, because `--mist` measures 2.58:1 against paper
and WCAG 2.2 SC 1.4.11 asks 3:1 of a graphical object that carries meaning —
mist at 50% over paper is nearer 1.6:1. The reading, and the E4 precedent it
follows (the hero line and the term-week sub-label were corrected the same way
in the E4 boundary round), are written into `instructorReportTrend.css`'s colour
paragraph and pinned by `PulseTrendChart.overlays.test.tsx`. So the code is
measured and the brief is not, and the two now disagree on this one line.

**Why it was left.** The brief is the owner's document and E5-07 is a component
ticket. Shipping a line an instructor with low vision cannot see was not an
option, and editing the owner's brief inside a light-lane build is not this
ticket's to do. Naming the divergence is the honest middle.

**Owner:** the brief's owner; E5-13 is where an E5 ticket next reads this
surface and can carry the edit if it is ruled.

**Done when:** either the brief's mapping names a token that measures at or above
3:1 on paper for both lines, or the ruling is recorded that mist stands and this
ticket's substitution is reverted with the measurement stated as accepted.

## E5-07's stroke pins live beside E5-07's tests rather than in the report's two pin modules

**What is not enforced.** `reportContrastTokens.test.ts` and
`reportMockupFidelity.test.ts` are where the report's stylesheet-only rulings are
pinned, and neither reads the two comparison-line rules E5-07 adds; those pins
are in `PulseTrendChart.overlays.test.tsx` instead. A reader looking for "every
contrast correction on the report" has two places to look rather than one.

**Why it was left.** Three frontend tickets (E5-07, E5-08, E5-09) build in
parallel against the same breakdown, and both pin modules read several
stylesheets each. Adding to a shared module from a parallel branch is the
same-file merge the breakdown's parallel rules exist to avoid, and the pins are
worth more beside the tests that explain them than they are worth being in one
file a week earlier.

**Owner:** E5-13, which already reads every surface E5 ships.

**Done when:** the overlay stroke and contrast pins are in
`reportContrastTokens.test.ts` with the rest of the measured corrections, or the
two-module split is recorded as deliberate with the rule that says which pin goes
where.

## A member that says `suppressed: false` and carries no `points` crashes the panel

**What happens.** `drawnPoints` returns `undefined` for a series whose flag is
exactly `false` but whose `points` key is missing, and the spread in
`axisWeeks` then throws, so the panel render fails. The security re-pass of
the fail-closed fix (`02af6cf`) named it and judged it a robustness note
rather than a finding: the failure withholds a figure rather than disclosing
one, and it needs a payload that sends the flag without the array.

**Why it was left.** The fix round's declared stopping rule covered one
finding; this is not that finding, and the shape that triggers it cannot come
from the fixtures this ticket ships.

**Owner:** E5-10, the ticket that wires the real payload — the place a
malformed first-party payload becomes possible.

**Done when:** a flag-without-points member renders the suppressed treatment
(or another stated treatment) rather than throwing, pinned by a test beside
the malformed-flag pair.

## The benchmark definer's reach has no pinned equality (E5-03)

`pulse_benchmark_definer` owns the two benchmark set functions and holds
column-grain `SELECT` on `response`, `answer`, `question`, `section`, `term` and
`week`. The other three definer owners each have a test asserting their grants
as an **equality** — `test_the_resolve_definers_privileges_are_exactly_the_point_lookups_it_answers`
and its roster sibling — so a later ticket widening one of those owners is a red
rather than a diff. This owner has no such test: its entry in
`IDENTITY_DEFINER_ROLES` names the gap, and E5-03's own suite asserts what the
functions answer rather than what their owner may read. **Done when** a test
asserts, as an equality in both directions, the exact set of
`(relation, column)` pairs `pulse_benchmark_definer` holds `SELECT` on, with no
column of `user`, `user_identity` or `person` among them. Owner: E5-04, which is
the next ticket to touch this door; a security round on E5-03's pull request may
pull it earlier.

## The benchmark views do not filter a response's validity (E5-03)

SPEC §3.3 classifies a submission as valid or not, and `response.is_valid`
records the verdict. Neither `report_rating_distribution` nor `report_workload`
filters on it, and E5-03's four cohort views and two set functions follow them,
so a benchmark counts every stored response exactly as a section's own report
does. That is consistency rather than a decision: nothing in E5-03's ticket, the
E5 breakdown or the ruling on `docs/disputes/E5-03-01.md` says whether a
comparison figure should be computed over valid responses only, and making the
benchmark disagree with the figure it is drawn beside would be a change to what
both numbers mean. **Done when** the question is answered in the open — either
"a comparison figure counts every response, as a section's own figures do,
recorded in a sentence" or a `_v002.sql` per view plus the same filter in both
function bodies. Owner: E5-04, which is where comparison policy lives; E5-08
reads the workload figures and would inherit the answer.

## A course week assumes a section starts on one of its term's week boundaries (E5-03)

The course week these views key on is derived as
`week.number - floor((section.start_date - term.start_date) / 7)`. That is exact
for every section §2.2's start-letter map produces, because each start date is a
Monday a whole number of weeks after the term's first, and the seeded worlds and
the property test over all twenty cohorts agree with it. A section whose stored
start date fell mid-week — which no writer produces today and no constraint
forbids — would be keyed to the week its start rounds down to, silently. **Done
when** either a database constraint makes a mid-week section start unstorable,
or a sentence records that the derivation rounds and that this is the intended
answer. Owner: E5-14 at the epic exit, unless a roster ticket writes a start
date from a platform first.
