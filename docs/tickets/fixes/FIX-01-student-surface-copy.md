# FIX-01 — The survey page reads the way its owner asked

**ID:** FIX-01
**Branch:** `fix/student-surface-copy`
**Depends on:** nothing open (builds on merged E2)
**Lane:** heavy — two items add fields to the student read answer, and
`backend/app/services/survey_read.py` is a §4.1 read path.
**Security-relevant:** items 2 and 4 widen the read answer (course/term
metadata and window instants only; no person data — the professor's name is
deliberately NOT here, see `../e7/carried-requirements.md`).

## Context

Four rulings from the owner's 2026-09-03 interactive drive of the merged E2
stack, wordings exact. The eyebrow's "TERM 03" had to be explained to its own
product owner; the page never says which term; a closed section's placeholder
withholds a date the system already holds.

## Scope

1. **The week eyebrow labels both axes in words**: `COURSE WK 03, TERM WK 03`
   (replacing "WK 03 / TERM 03"). Copy lives in
   `frontend/src/copy/studentSurvey.ts` (`term_week_label` and its course
   sibling), rendered by `frontend/src/components/WeekEyebrow.tsx`. While
   here: the open deferred entry "the week eyebrow cannot say how long the
   course runs" (E2-10, `../e2/deferred.md`) is this surface's other half —
   close it in the same pass if its done-when allows, or say why not.
2. **The heading reads `MATH 140 E1FF — College Algebra, Fall 2026`.** Order
   ruled: prefix, number, then section code, then the em-dash title, then the
   term's name. The term name comes from `term.name` (verified on the seeded
   database: "Fall 2026"; no schema change). The read answer
   (`survey_read.py` → `schemas/student.py` → `frontend/src/api/student.ts`)
   gains the term name; whether the label restructures `course_label` or adds
   a `term_name` field is the work order's call — one field, no person data.
3. **The heading is the page's visual headline.** With several courses on one
   screen, each course's heading gets a clearly larger type treatment so the
   courses are distinguishable at a glance. `docs/DESIGN_BRIEF.md` and
   `design/tokens.css` govern the scale step; if
   `design/StudentWeeklySurvey.dc.html` shows the heading, it moves too.
4. **The closed-section placeholder says when.** Ruled wording, shape exact:
   "When the next survey for this course opens at 6:00PM EDT on Friday,
   September 4, it appears here." — the next materialized `survey_window`'s
   `opens_at` for that section, rendered in `INSTITUTION_TIMEZONE` with the
   zone abbreviation derived from the date (the owner's example said EST; a
   September date in America/New_York renders EDT — derive, never hardcode).
   The read answer gains the next window's opening instant for sections
   whose survey is not open; a section with no future window keeps the
   current sentence.

## Constraints

- New wire fields get read-path pins, and the §4.1 refusal pair
  (forbidden section vs unknown id) stays byte-identical — no new field may
  leak onto a refusal body. The isolated invariant pass may not shrink.
- Frontend strings go through `frontend/src/copy/studentSurvey.ts` in that
  file's exact literal style (E2-11's parser is strict); no comparative
  language (the FORBIDDEN_COMPARISONS sweep runs over every string).
- Tokens only, no raw hex; the e2e conventions from
  `tests/e2e/student-survey*.spec.ts` (single worker, clock restored).

## Acceptance criteria

1. At a two-open-window clock the page shows each course under its own
   headline-scale heading reading `<PREFIX> <number> <code> — <title>,
   <term name>`, and the eyebrow reads `COURSE WK NN, TERM WK NN` — asserted
   in e2e.
2. A section whose survey is closed but has a future materialized window
   names its opening instant in the institution timezone with a derived zone
   abbreviation; one with no future window keeps the current sentence — both
   directions asserted.
3. The new wire fields are pinned by integration tests; the refusal pair is
   re-asserted byte-identical; `-m invariant` green, not shrunk.

## Out of scope

- The professor's name (E7's — `../e7/carried-requirements.md`).
- Everything in FIX-02.
