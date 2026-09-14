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
