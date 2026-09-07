# E4-17 — The week eyebrow says how long the course runs

**ID:** E4-17
**Branch:** `e4/eyebrow-course-length`
**Depends on:** nothing — free-standing, and it can build beside E4-07
**Lane:** heavy — the diff adds a field to `backend/app/schemas/student.py` and
a read to `backend/app/services/survey_read.py`. The services row names the
second outright, and the schemas module is under `backend/app/` with no row of
its own, which the fail-closed rule makes heavy. It is a student read path
either way.
**Security-relevant:** it widens what a student read answer carries, so §4
and §4.1 are the question the ticket has to answer rather than assume. The
answer is short and is argued in Context, not left to the reviewer.

## Context

`docs/DESIGN_BRIEF.md` writes the week eyebrow as
"WK 07 / 12 · closes Sun 11:59 PM" and calls the eyebrow the first thing on
every student and instructor screen. The second half of that number has never
shipped. `OpenSurvey` carries `course_week`, `term_week` and `closes_at`, and
nothing that says how many weeks the section runs for, so `WeekEyebrow` has no
total to render and says so in its own docstring.

**Read the component, not the deferred entry, for what ships today.** The
entry in `docs/tickets/e2/deferred.md` describes the shipped eyebrow as
"WK 07 · TERM 11", which is the pre-FIX-01 form. The owner's ruling of
2026-09-03 (FIX-01 item 1) replaced it: both of SPEC §2.2's axes are named in
words, and `frontend/src/components/WeekEyebrow.tsx` renders
`COURSE WK 04, TERM WK 07 · closes Sun 11:59 PM` from two governed copy
strings in `frontend/src/copy/studentSurvey.ts`. Three end-to-end specs assert
that string today — `tests/e2e/student-survey.spec.ts`,
`tests/e2e/student-survey-heading-and-next-window.spec.ts` and
`tests/e2e/exit-weekly-survey.spec.ts`.

**The owner's ruling of 2026-09-07 is what makes this ticket buildable.** The
FIX-01 note on the deferred entry left the wire half of the done-when standing
and parked the rendering half on one open question: where the total sits inside
the ruled string. The ruling answers it. The student survey payload gains the
course length, and the eyebrow renders the brief's "/ N" form; deriving the
total in the frontend is rejected, because the section code carries the start
letter and the letter-to-length map is the institution's, so a client-side
derivation would be a second copy of `start_letter_map` in TypeScript — the
shape `docs/MISTAKES.md` entry 19 is about, and one that reads right in review
because the arithmetic looks simple.

**Where the total sits, and what stays.** The total attaches to the course-week
half, giving `COURSE WK 04 / 12, TERM WK 07 · closes Sun 11:59 PM` — the shape
the FIX-01 note itself floated as its example. The quiet term-week label
**stays**. SPEC §2.2 and `design/Usage Rules.md` §1 both put both axes on a
course-level surface, FIX-01 ruled that both be named in words, and the
2026-09-07 ruling adds a total rather than removing an axis. The alternative —
rendering the brief's bare "WK 07 / 12" and dropping the term week — was
rejected: it costs the second axis §2.2 requires and reverses a standing owner
ruling this one did not reopen, and it would tell a student whose section
started mid-term nothing about where the term is.

**The number is already on the section row.** `section.length_weeks` is a
stored column (`backend/app/models/org.py`), written from the section code
against the term's start-letter map by `backend/app/services/section_codes.py`.
`_open_survey` in `backend/app/services/survey_read.py` already holds the
`Section` the window belongs to, so the read is that column and no new join.

**Why §4 and §4.1 are satisfied.** The length is the reader's own section's
attribute, reached through the section the reader is enrolled in — the same
argument `EnrolledSection.course_label` already stands on (E2-17 item 5,
respelled by FIX-01 item 2), and §4.1 item 1 is what it has to hold against. It
names no other section, carries no identity, and discloses nothing new: §2.2
puts the length in the section code the student is already shown. It is a
number about a calendar, not about a person, so no confidentiality rule in §4
reaches it. The ticket states this rather than leaving it to be inferred.

No ADR. The construction choice here was settled by the owner's ruling of
2026-09-07 rather than left open to a reasonable engineer, and this ticket is
where that ruling is recorded; an ADR restating it would add a second place for
it to drift.

Read first: the deferred entry whole, including its FIX-01 note; SPEC §2.2 and
§4.1; `docs/DESIGN_BRIEF.md`'s three eyebrow lines and `design/Usage Rules.md`
§1; `WeekEyebrow.tsx` and its docstring; `survey_read.py`'s `_open_survey`.

## Scope

- One field on `OpenSurvey` in `backend/app/schemas/student.py` naming how
  many weeks this section runs for, described the way its neighbours are.
- One read in `backend/app/services/survey_read.py`, off the `Section`
  `_open_survey` already holds. No new query, no new join, no derivation.
- The two eyebrow copy strings in `frontend/src/copy/studentSurvey.ts` grow
  the total, and `WeekEyebrow.tsx` takes the count as a prop and fills it. The
  copy stays governed: the whole of what a reader sees stays inside the
  inventory, as the module's own comment requires.
- The three end-to-end specs that assert the eyebrow string move to the new
  form, in the same change that changes it.
- The component's docstring loses the paragraph saying the total is absent and
  says where it comes from instead.
- The deferred entry and its carried copy close, and this file and the
  breakdown's records say what closed them.

## Acceptance criteria

1. `OpenSurvey` carries the section's own week count, and the read path's
   integration test asserts it **against the seeded calendar** — the start
   letter and the term's start-letter map per SPEC §2.2 — rather than against
   `section_codes`, the service that computed it. That is the deferred entry's
   own done-when, and asserting it against the computing service would prove
   only that the service agrees with itself.
2. The count is the section the window belongs to, and never another's: a
   fixture with two sections of different lengths open to the same reader
   answers each with its own count, and a mutation that reads the length from
   any section but the window's own is caught.
3. `WeekEyebrow` renders `COURSE WK 04 / 12, TERM WK 07` — the total on the
   course-week half, the term-week label unchanged — with the total filled
   from the API's number through `fillCopy` and never derived in the
   component. Proven by a component test on E4-16's runner.
4. The count is the API's alone: no letter-to-length map, no term calendar,
   and no arithmetic over the section code exists anywhere in
   `frontend/src/`, asserted so the derivation this ticket rejects cannot
   arrive later by accident.
5. The three end-to-end specs assert the new string against the seeded
   twelve-week section, and the eyebrow spec's existing near-miss stays
   meaningful — serving the term week in the course week's place, or the term
   length in the section's, must still fail.
6. The copy inventory holds: both eyebrow strings are still governed copy with
   their placeholders filled from the read answer, and
   `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`
   stays green over the changed strings.
7. §4.1 is undisturbed: the isolated invariant pass runs unchanged and the
   student read path's existing scoping assertions still hold, with the new
   field carried through them rather than around them.
8. The deferred entry in `docs/tickets/e2/deferred.md` and its carried copy in
   `docs/tickets/e3/carried-from-e2.md` each close in place with what closed
   them, in the form E4-16 used; `docs/tickets/e4/README.md`'s decision 9, its
   carried-work table row and its build-order row say the entry was taken
   after all, and E4-15's ledger reads them rather than hunting.

## Known traps

- **The deferred entry's own text is stale.** It describes a string FIX-01
  replaced. Building to the entry's literal wording would un-ship a standing
  owner ruling; build to the component and to the 2026-09-07 ruling, and let
  the entry's done-when govern only the wire half and the test's currency.
- **Asserting the count against the computing service proves nothing.** The
  done-when singles this out. The seeded start letter and the term's map are
  the independent currency; `section_codes` is not.
- **Three specs, not one.** The eyebrow string is asserted in three end-to-end
  files. Changing the copy and finding two of them leaves a red suite that
  looks like an unrelated break.
- **The mono eyebrow pads to two digits.** `padWeek` exists so week 7 and week
  12 are the same width down a column; the total goes through the same
  padding, or a twelve-week section and a three-week one stop lining up.
- **A count of zero or a null is not a shorter course.** The column is
  `NOT NULL` on the section row, so the field is a plain integer rather than
  an optional one; an optional field would invite the component to render a
  half-eyebrow rather than fail loudly where the data is wrong.

## Out of scope

- The instructor report's eyebrow. E4-08 through E4-11 build against the
  payload sketch, whose `section` member already carries `length_weeks`;
  nothing here changes that sketch or those tickets.
- Any other member of `OpenSurvey`, and the term's own length. The term week
  is already carried and already rendered; the term's total is not a number
  the brief's eyebrow states.
- The bounce-position entry and the font-licence entries that sit beside this
  one in `docs/tickets/e2/deferred.md` — different owners, untouched here.
