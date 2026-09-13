# E4-21 — The report matches its mockup again

**ID:** E4-21
**Branch:** `e4/report-design-fidelity`
**Depends on:** E4-11 (the page this ticket restyles), E4-20 (the demo world
the result is checked against)
**Lane:** light — the diff stays inside `frontend/src/`; no route, payload,
or read path changes.
**Security-relevant:** no. Nothing here touches what data is shown, only how
the already-served data is laid out and worded.

## Context

A design-fidelity audit on 2026-09-11 compared the running instructor Monday
report against `design/InstructorMondayReport.dc.html` and its component
files, and the owner confirmed the mockup is what the page should look like.
The audit sorted the drift into three piles: plain fidelity slips, deliberate
construction decisions that conflict with the mockup, and work that belongs
to later epics. This ticket is the first pile only. The other two piles are
listed under "Deliberately not fixed here" and stay untouched.

The rule this ticket works under (decision 14 in the README): where the
built report and the mockup disagree and no recorded ruling, ADR, or spec
section decides otherwise, the mockup governs. Where a recorded ruling
contradicts the mockup, the ruling stands until it is revisited one item at
a time — this ticket revisits none of them.

## Scope

1. **The white card returns.** The mockup wraps the whole report in a
   paper-white article — hairline border, 8px radius, the one soft shadow —
   centred at 760px on the chalk page with the mockup's outer padding
   (`design/InstructorMondayReport.dc.html:11-12`). The implementation
   renders content directly on the chalk page in a 720px column
   (`frontend/src/components/instructorReportPage.css`). Restore the card
   and the 760px column.

2. **The header subline returns.** `R3WW · Monday Report · 18 of 24
   responded` in 13px spruce-60 directly under the course title
   (`design/InstructorMondayReport.dc.html:21, 257`). Every value is already
   on the report payload (`section.code`, `rates.responses`,
   `rates.enrolled`); the page just never renders them.

3. **The week arrows go back to the eyebrow row.** Top-right, in the same
   flex row as the eyebrow, 28×28px with a 14px glyph
   (`design/InstructorMondayReport.dc.html:13-19`). They currently sit below
   the title, left-aligned, at 32×32px. Keyboard reachability and the
   disabled treatment stay as they are.

4. **The histogram gets its structure back.** One continuous hairline rule
   under the bars instead of five per-bucket dashes, and the mockup's
   two-box layout — a 96px row for counts and bars, a separate tick row
   beneath (`design/RatingHistogram.dc.html:14-24`) — so the count labels
   cannot overflow into the mean line. The mean's own digits render in full
   spruce against the surrounding spruce-60 (`design/RatingHistogram.dc.html:13`).
   Verify the overflow on screen before and after; the audit read it off the
   CSS and called it probable, not proven.

5. **The trend x-axis spans the whole term.** The axis always shows all
   `length_weeks` ticks with the line occupying the elapsed portion
   (`design/PulseTrendChart.dc.html:93`), instead of stretching the elapsed
   weeks across the full width. The dual WK/TERM labelling stays exactly as
   built — its wording is a recorded ruling.

6. **The small-N notice moves and speaks fully.** It renders once, after
   both comment groups (`design/InstructorMondayReport.dc.html:69-73`), not
   inside the instructor group. Its copy regains the leading sentence and
   the "AI summary above" phrasing: "Only {n} of {m} students have
   responded. To keep individual voices unidentifiable, raw comments stay
   hidden until at least {t} responses arrive. The AI summary above draws on
   everything received so far." (`design/SmallNNotice.dc.html:31-33`).

7. **Small copy and spacing.** The AI panel footer reads "Generated from
   {n} responses" (`design/AiPanel.dc.html:20`), not "Drawn from". The
   eyebrow no longer renders the comma-plus-middot artifact ("… / 12, ·
   TERM …") — the artifact only; the wording itself is a recorded ruling
   and stays. The header sparkline takes the mockup's `margin: 16px 0 32px`.

## Acceptance criteria

- Side by side against the mockup, driven on the demo world
  (`BIOL-310-R7FF`, clock at 2026-10-19T09:00), every scope item above is
  visually indistinguishable from the mockup's treatment of it.
- The count labels over the tallest histogram bars sit inside the chart
  region at every bucket height the demo world produces, verified on
  screen.
- Component tests cover the changed copy (subline, small-N notice, AI
  footer) and the axis-domain rule (a 7-of-12-week payload renders 12
  ticks). Existing component tests and the e2e suites stay green — the
  exit e2e asserts report content, and nothing here changes content.
- The moved arrows remain reachable by keyboard in the same tab order
  position relative to the eyebrow as the mockup implies, and the page
  still passes the standing a11y checks.

## Deliberately not fixed here

Conflicts with recorded decisions, each waiting on its own ruling before
anyone touches it:

- The trend line's colour (marigold in the mockup, marigold-deep in the
  build for a documented 2.23:1 contrast failure of the accent on paper).
- The eyebrow's wording (the built "COURSE WK … TERM WK …" is the FIX-01
  ruling of 2026-09-03; the mockup's "WK 07 / 12 · RESPONSES CLOSED …" close
  note is part of the same question).
- The histogram titles (the mockup quotes the survey questions; the build
  refuses to duplicate a versioned server-side instrument — the fix is a
  payload field, not a pasted string).
- Comment text's face (the mockup sets it sans; `design/Usage Rules.md` §5
  says a student's own words get the serif treatment — the two design
  records contradict each other).
- The two blocks the mockup lacks: the participation-credit paragraph
  (E4-12, an E3 carried item) and "Comments from earlier weeks" (ADR 0152).

Later-epic work, not styling: the comparable and university figures
everywhere they appear (trend lines, legend entries, histogram "comparable
X.X", workload "vs …" — no comparable aggregate exists on any payload), the
"Your response" compose block, the Lead Faculty header line (needs a payload
field), and the flagged-comment row (nothing in E4 produces a flag).

## ADR

None expected: every choice here either follows the mockup or defers to an
existing record. If restoring the two-box histogram forces a contestable
structural choice the mockup does not settle, that gets an ADR in the PR.
