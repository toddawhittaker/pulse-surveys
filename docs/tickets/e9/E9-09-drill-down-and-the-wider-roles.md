# E9-09 — The drill-down and the wider roles

**ID:** E9-09
**Branch:** `e9/drill-down-and-the-wider-roles`
**Depends on:** 01, 05
**Lane:** light
**Why this lane:** a read in `services/reporting.py`, one route, and changes
to `services/moderation.py` and `services/response_loop.py`, none a heavy
path. Its migration adds a column to `weekly_summary`, none of the four heavy
kinds. It calls E9-05's reader-aware seal and changes nothing in it. It must
not add or change an `invariant`-marked test: those are E9-12's. If any
change reaches a heavy path, it stops and re-lanes; in particular, if scoping
the exclusion log or the policy to a purview needs a new helper in
`services/authz.py`, the ticket re-lanes to heavy.
**Size:** L
**Security-relevant:** the only place a leader reads raw comments and a
section's benchmark lines. A defect here lets a leader open a section outside
their purview, shows a held comment, passes a summary that carries an
excluded comment, or offers an action on a read-only page.

## Context

SPEC §5.5: "Drill-down terminates at a section, rendering the Instructor
Monday Report wholesale, read-only, with a context bar." Ruling 2: comments
reach a leader only here, under the section's own per-stream threshold and
release batches.

- **`leadership_report`**, beside `_payload` in `services/reporting.py`,
  answers a section-week's report for a leadership reader. It finds the
  section inside the reader's leadership scope (E9-01) and the week among
  published weeks, exactly as the instructor's report finds its own; a
  section outside the purview and one that does not exist get the same 404.
  It reuses `_payload`'s per-stream hold, release batches and §5.2 flag
  hiding unchanged. It carries no action: `decided_by_you` is false
  everywhere, no composer, no exclude, keep or undo. The benchmark lines pass
  the reader into E9-05's seal, whose known set is the person's leadership
  purview together with every section they teach (§5.1).
- **The stored-summary filter on sequence.** The on-behalf filter withholds a
  summary not strictly later than the week's latest exclusion or keep-undo by
  comparing transaction-start times, which a racing exclusion can pass (the
  carried race). `weekly_summary` gains the highest moderation decision
  sequence the walk saw, and the filter compares sequences. The drill-down,
  and every up-chain reader, use that one function (the carried stored-summary
  entry).
- **The three wider roles (decision 12).** The assistant dean, the dean and
  the vice president read the exclusion log and the response policy over
  their purview, read-only. The review queue and on-behalf publishing stay
  with the lead and, for an unled course, the chair. ADR 0190's 403 for those
  roles is replaced on the log and policy routes and restated on the queue
  and on-behalf routes.
- **§4.1 item 5.** The drill-down shows one student's comment text, so the
  report's confidentiality line shows once on the drill-down as it does on
  the instructor's report. The `leadership_response` surface's answer (no
  line, because it shows summaries, counts and ratings only) is re-asked and
  recorded in ADR 0206.

Read first: SPEC §4, §4.1, §5.1, §5.2, §5.3 and §5.5; ADRs 0146, 0152, 0184,
0187, 0190, 0194, 0199 and 0203; `services/reporting.py` (`_payload`,
`_published_section_week`, `_summary_rows_since_latest_removal`),
`services/moderation.py` (`exclusion_log`, `review_queue`, `_review_courses`),
`services/response_loop.py` (`policy_overview`).

## Owns

- `backend/app/services/reporting.py`: `leadership_report`, and the summary
  filter on sequence.
- The summary walk's write of the sequence (`reporting.py` or wherever the
  walk writes `weekly_summary`).
- Migration **`e9d4a6c8e504`**, planned `down_revision = "e9f6c8e0a706"` (or
  `e9a7c9e1b807` if 07 adds none; re-pointed to the head it finds).
- `backend/app/api/leadership.py`: the drill-down route; the log and policy
  routes admitting the three roles.
- `backend/app/services/moderation.py`: the log over the purview for the three
  roles, and the small redundancies in the functions it edits.
- `backend/app/services/response_loop.py`: the policy view for the three
  roles.
- `backend/app/schemas/report.py`: only if the drill-down needs a member; it
  reuses `InstructorReport` otherwise.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- ADR **0206** (the drill-down, the three roles, the sequence filter, the
  item 5 answer). It amends ADR 0190 and 0194, each with a line.

## Reuse, do not rewrite

`_payload`, `_published_section_week`, `_published_weeks`, `_held_streams`
and the release reads in `services/reporting.py`; the on-behalf summary
filter's function (moved onto sequence, never copied); E9-01's
`leadership_scope`; E9-05's seal; `exclusion_log` and `policy_overview`.

## Done when

1. **Inside the purview only.** A dean opens a section in their college; a
   lead cannot open a sibling lead's section; both refusals and a section id
   that does not exist answer the same 404 with the same body.
2. **The section's own hold, unchanged.** In a stream below the threshold the
   drill-down carries no comment text and carries the small-N state, as the
   instructor's report does; a released batch shows only in the batch, with
   no week; a flagged comment is hidden as §5.2 hides it. Asserted by reading
   the same section-week as the instructor and as the dean and comparing the
   comment sets: they are equal.
3. **Read-only.** The payload carries no action: every `decided_by_you` is
   false, no composer state, no exclude, keep or undo; and the moderation and
   response write routes refuse the dean for that section.
4. **The seal counts the reader.** The drill-down's university line for a
   section is suppressed when what is left after removing the reader's
   known set (leadership purview and taught sections) is non-empty and thin,
   while the report of the same section read by an instructor with no
   leadership assignment shows it (the seal's behaviour is E9-05's; this asserts the
   drill-down passes the reader).
5. **No summary older than the latest exclusion, by sequence.** A summary
   written after an exclusion's transaction began but before it committed is
   withheld from the drill-down and from the on-behalf read; a summary written
   after the exclusion's sequence is shown. A test that excludes a summarized
   comment and reads the summary as the dean.
6. **The three roles read the log and policy.** The assistant dean, the dean
   and the vice president each read the exclusion log and the response policy
   for sections in their purview, and nothing outside it; each still gets the
   403 on the review queue and the on-behalf routes, with its existing
   sentence. A dean (and likewise an assistant dean or VP) who teaches, or
   once taught, a section in their purview gets no exclusion-log row from
   that section, where the instructor's own view governs (§5.2); the twin: a
   row from an untaught section in the same purview is present.
7. **Item 5.** The drill-down reuses the instructor report's surface, so the
   report's confidentiality line shows once on it; its context bar's words go
   under `leadership_rollup.`. No change to the copy inventory test.
8. **The records match.** ADR 0206 is written and indexed; ADR 0190 and 0194
   gain their lines; comments naming tickets in `reporting.py`,
   `report_comments.py` and `response_loop.py`'s edited functions are
   rewritten.

## Shares files with

- `services/reporting.py`: 08.
- `services/response_loop.py`: 03, 07 and 08.
- `services/benchmarks.py`: 05 (read only here) and 07.
- `api/leadership.py`: 05 and 07.
- `openapi.json`, `wire.gen.ts`: 04 to 08.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 49, 50 and 51.

## Known traps

- **Entry 51.** Read the drill-down this Monday and next, around a release
  batch, and after an exclusion: the hold is a property of the sequence.
- **Entry 3.** Every absence (no action, no comment) needs its present twin.
- **The race.** Plant the interleaving with two connections, not by sleeping.

## Not in this ticket

- The page (11).
- The `invariant`-marked tests over the drill-down (12).
- A composer or AI panel on the drill-down (§5.5).
