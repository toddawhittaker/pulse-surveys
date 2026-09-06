# E4-10 — The comment components

**ID:** E4-10
**Branch:** `e4/comment-components`
**Depends on:** E4-16 for merge order only — builds day one against the
README's payload sketch; the PR waits for the runner
**Lane:** light
**Security-relevant:** these components render student words to instructors;
they must render exactly what the payload hands them — no timestamp display
surface at all, no count of anything the payload did not count, and the
small-N notice's copy is confidentiality copy (§4.1 item 5 governs where it
appears and how often).

## Context

The comment half of the report, per §7.6: **CommentCard** (variants:
default, flagged-collapsed, flagged-expanded, excluded; the optional stream
chip stays default-off), **AiPanel** (the summary leading each group, with
its stated response count and the held-note slot), and **SmallNNotice** in
its instructor audience (the student audience is E8's). The report's
structure: comments grouped under "About the instructor" / "About the
course", each group led by its stream's summary, an empty group showing a
one-line notice rather than a hidden heading (§5.1).

In E4's shipped data every comment is in the initial published state — the
flagged and excluded variants are built and proven against fixtures because
§7.6 names them and E6 will feed them, but no E4 path produces them live.

Read first: `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §7.6, §5.1,
§5.2 (the variants' meanings), §4 (what never renders: timestamps, identity,
anything ordering-revealing); the payload sketch; E4-16's conventions ADR
(test file placement and what renders a component under test — settled once
there, not per ticket).

## Scope

- The three components, fixture-driven, typed to the sketch.
- The group assembly piece (summary panel atop its group's cards; the
  empty-group one-liner) as a composable unit E4-11 places twice.
- The small-N state: notice plus summary, zero cards — built here as a
  fixture-driven state of the group unit.
- Accessibility: cards and panels reachable and labeled; the collapsed
  variant's disclosure is keyboard-operable.

## Acceptance criteria

1. The group unit renders summary-first, cards after, from sketch fixtures;
   with an empty comment list it renders the one-line notice and no heading
   pretending otherwise.
2. The small-N fixture renders the notice and the summary and zero cards —
   and the DOM carries no count of suppressed comments anywhere, including
   data attributes.
3. CommentCard renders no timestamp in any variant — there is no prop to
   pass one, which is the assertion.
4. The four CommentCard variants match the brief's states from fixtures;
   flagged-collapsed's disclosure works by keyboard; the excluded variant
   renders muted text visible above its notice (§5.2's instructor view).
5. AiPanel states the response count from its prop ("drawn from N
   responses" per the brief's phrasing) and renders the held-note slot only
   when the payload populates it.
6. The stream chip stays off by default and no E4 usage turns it on.
7. Strings in the copy layout; no raw hex; no fetching.

## Known traps

- **Building the variants is not building the lifecycle** — no state
  machine, no undo logic, no decision affordances; those are E6's, and a
  button here would be a promise the backend cannot keep.
- **The empty group and the suppressed group are different states** with
  different notices — §5.1's empty-group line versus §4's small-N framing;
  the fixtures must drive both and the copy must not blur them.
- **"One comment is held for review" renders only above small-N** (§5.1) —
  the component takes what the payload gives; do not add client logic
  deciding when the note shows.

## Out of scope

- Real data, grouping by week, page placement — E4-11.
- The moderation lifecycle, chips' actions, undo — E6.
- The student-audience SmallNNotice — E8.
