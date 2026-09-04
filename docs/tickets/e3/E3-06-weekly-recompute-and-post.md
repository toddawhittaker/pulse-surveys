# E3-06 — The weekly recompute posts a score when it has changed

**ID:** E3-06
**Branch:** `e3/weekly-recompute-and-post`
**Depends on:** E3-03, E3-04, E3-05
**Lane:** heavy
**Security-relevant:** the job runs with the tool's own credentials against
every section it walks, and its logs are the place a participation figure
would leak into a log stream. `backend/app/jobs/` matches no row in
`.claude/heavy-lane-paths.md` and sits under `backend/app/`, so the table's
fail-closed rule makes it heavy; `backend/app/services/` is a named row.

## Context

The piece that joins E3-03's arithmetic to E3-04's client. The shape to copy
is already in the tree: `derive_survey_windows`
(`backend/app/jobs/tasks.py:139`) is a thin task that opens a session, calls
a service and commits once, with the schedule entry living in
`BEAT_SCHEDULE` (`backend/app/jobs/schedules.py:36`, wired at
`backend/app/jobs/celery_app.py:63`). This ticket adds one more of each.

The structural fact that shapes it: **a posted score is not final when its
week closes.** E2-08's asynchronous reclassification sweep can flip a
comment that fell to the fail-open floor from substantive to `insufficient`
weeks after the window shut, which lowers the numerator of a score that has
already been posted. So "recompute after each week closes" as a literal
schedule is wrong some of the time, silently.

**Ruled at breakdown, 2026-09-04:** the recompute is an idempotent sweep that
posts when the computed value differs from what `grade_sync` records as last
sent, and posts nothing otherwise. The weekly beat entry is the ordinary
trigger for that sweep, not the definition of the work.

Read first: SPEC §3.4, §6.1; ADR 0052 (an equal score timestamp is accepted
as a retry — the identity this ticket must not collide with), ADR 0109 (the
development clock is an offset, not a freeze); `carried-from-e2.md`, the
rewound-clock entry, which is a to-know for this ticket rather than work it
owes; E3-03's formula and E3-04's client.

## Scope

- A beat entry and a thin task on `derive_survey_windows`'s shape.
- The sweep: for each section with a line item, for each enrolled student,
  compute through E3-03, compare against the value in the **latest**
  `grade_sync` row for that student and section, and post through E3-04 only
  where they differ.
- A `grade_sync` row appended on every post — what was sent, exactly as sent,
  when, and the outcome (ADR 0124). The table is append-only, so a post never
  overwrites the record of the one before it, and a failed attempt is
  appended too.
- Retry and backoff on a failed post, with a 409 handled as E3-04 defines it.
- Drops: posting stops for a dropped student; the LMS owns the column.
- The log policy from the README's ruling: the task logs the section, the
  outcome and the call, and never a score, a ledger line, or an LMS user id.

## Acceptance criteria

1. A section whose first window has closed gets a score posted for each
   enrolled student; a section whose first window has not closed gets no post
   at all, not a posted zero.
2. Running the sweep twice in a row posts once. The second run reads
   `grade_sync`, finds no difference, and makes no HTTP call — asserted
   against the call log, not against the gradebook, because an idempotent
   post and an absent post look the same in a gradebook.
3. A reclassification that lowers an already-posted week's numerator causes
   the next sweep to post the lower value, and `grade_sync` afterwards holds
   **both** rows — the higher value that was sent first and the lower one
   that superseded it, each with its own timestamp. This is the case the
   schedule ruling and ADR 0124's grain both exist for, and it gets its own
   test.
4. **Every posted score carries the ledger.** No post leaves this task
   without the per-week comment E3-03 produced, asserted by reading the
   posted comment back rather than by reading the code that composed it. A
   post with an empty or absent comment is a failure of this criterion, since
   the comment is the only place §3.4's arithmetic is visible to anyone
   (ADR 0125).
5. A failed post retries under the stated policy and stops; the section is
   left in a state an operator could act on rather than in a loop.
6. A dropped student's score stops updating, and the value the platform holds
   is the one the last successful post sent.
7. No log line the task emits contains a score, a ledger line, or an LMS user
   id — asserted over captured log output, with a control line proving the
   capture actually sees what the task logs.
8. The suite runs the sweep against a section with no line item and against a
   section with no AGS address, and neither raises.

## Decisions this ticket settles

- **The beat slot and cadence**, and how the sweep bounds its own work so a
  weekly run does not walk every section of every past term.
- **What the score timestamp names** under a development clock: the
  recomputation's effective now, or real now. ADR 0109 makes these different
  values, and the choice is visible — see the traps below.
- **What an operator sees for a section whose posts are failing.** E11 builds
  the view; this ticket decides what is recorded for it to read, which is a
  decision about `ags_call` and `grade_sync` contents rather than about a
  screen.
- **Whether a lowered score is announced anywhere.** Still open, and
  deliberately so: SPEC §3.3 now states that the adjustment happens and says
  in as many words that whether it is announced is a separate question. That
  question is this ticket's to answer. Nothing in E3 renders a score to a
  student, so the honest answer is likely no and the consequence is carried
  to E8 — but it is a decision, not an omission, and it is written down as
  one either way.

## Known traps

- **Reclassification can lower a posted score.** This is the epic's key
  structural fact and the reason the sweep exists. A student who saw 92% can
  later see 85% without doing anything, because a comment the provider was
  never asked about at submit time was asked about later. The behaviour is
  correct under §3.3's fail-open rule; the surprise is the point to record.
- **Retry identity is byte-level.** ADR 0052 accepts an equal timestamp as a
  retry, which means a re-post carrying a *new* timestamp is a new delivery
  and not a retry. The formatting rule E3-03 settles is consumed unchanged
  here: if this ticket re-derives the percentage string, a retry after a
  network timeout can differ from the delivery it is retrying and the
  platform will take it as a second score.
- **The development clock makes a 409 reachable in a demo.** Elapsed weeks
  count off `clock.now` while the beat fires on real time, and the development
  override accepts a past instant. Rewind it, run a passback, and the score
  timestamp is strictly earlier than the one the platform already holds —
  which is a 409, which E3-04 correctly reads as stop-and-re-read. That is the
  right behaviour and a baffling demonstration, and it is why the timestamp
  question above is settled here rather than discovered in E3-07.
- **A rewound clock can also wedge a roster sync** (`carried-from-e2.md`).
  Same override, different victim. Not this ticket's to fix, and worth knowing
  before blaming the passback for it.
- **"Running it twice is safe" tested only against a database the job itself
  filled** is `docs/MISTAKES.md` entry 31. The idempotence test starts from a
  `grade_sync` row written by something other than the run under test.

## Out of scope

- The development trigger that runs the sweep on demand — E3-07.
- The job dashboard and the call-log view — E11, per §6.1.
- Any surface that shows a student their score — E8.
