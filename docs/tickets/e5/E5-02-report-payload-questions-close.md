# E5-02 — The report payload carries the question texts and the close instant

**ID:** E5-02
**Branch:** `e5/report-payload-questions-close`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** read-path additions in `backend/app/api/` and the
report schema — heavy rows. Neither field is about a person: question text is
versioned configuration, the close instant is a window row's own column.

## Context

The carried E4-21 follow-up, the one E5-owned entry in
`carried-from-e4.md` (its last section — read it whole first; its done-when
governs). Two mockup details the frontend cannot render because the payload
does not carry the data:

- **The served question texts.** The mockup titles each histogram with the
  question the student answered; the built report titles them by stream.
  Wording is versioned server-side (§3.2), so it is served, never copied
  into the frontend.
- **The week's survey-window close instant.** The mockup's eyebrow reads
  "responses closed Sun 11:59 PM"; `WeekEyebrow` already takes an optional
  `closesAt` and nothing supplies it. The instant is on the `survey_window`
  row the report read already holds.

This ticket does both halves — payload and rendering — the E4-17 pattern:
the wire half is heavy, the rendering half is small, and splitting them
leaves a field nothing renders.

Read first: the carried entry; SPEC §3.2 (question versioning), §5.1;
`backend/app/schemas/report.py` (where the members land, and the sealed
`comparison` member this ticket must not touch); `design/InstructorMondayReport.dc.html`
(the histogram titles and the eyebrow's close note, the proof targets);
`frontend/src/` — the histogram and `WeekEyebrow` components E4 shipped.

## Scope

- The payload: each stream gains its rating question's served text; the
  week member gains the window-close instant, from the `survey_window` row
  the read already holds.
- The read: question texts come from the question set in force for the
  reported week (§3.2) — versioned, so a re-versioned set changes the title
  for the weeks it governs and not for earlier ones.
- The rendering: histogram titles quote the served questions; the eyebrow
  renders its close note from `closesAt`, formatted per the mockup.

## Acceptance criteria

1. The payload carries both question texts and the close instant; the
   schema types them and the route serves them.
2. A planted second question-set version changes the served titles for its
   weeks only — the versioning proof, both sides.
3. The close instant equals the reported week's window row's close, not the
   current week's — asserted on a back-navigated week.
4. The histogram titles render the served strings — a fixture with a
   deliberately non-mockup wording renders that wording, proving nothing is
   pasted client-side.
5. The eyebrow renders the close note in the mockup's form; absent
   `closesAt` (older fixtures) renders the eyebrow unchanged, no crash.
6. Each half proven against the mockup, per the carried entry's done-when.

## Known traps

- **The `comparison` member is sealed** — this diff edits the same file
  E5-05 will; touch only the new members, and leave every chokepoint line
  alone so the two diffs cannot collide (the breakdown ordered 05 after 02
  for exactly this file).
- **Timezone in the rendered note** — the instant is stored aware; the
  rendering formats in the institution timezone, not the browser's guess.
  Pin a fixture across a DST boundary.
- **Copy inventory** — the close note and any new label live in the copy
  layout the inventory collects (E5-13 reads them).

## Out of scope

- Benchmark members of any kind — E5-05.
- Any new component — the histogram and eyebrow exist; this ticket feeds
  them.
