# E4-13 — The Care landing docstring

**ID:** E4-13
**Branch:** `e4/care-landing-docstring`
**Depends on:** nothing
**Lane:** heavy — not a typo. E3's record predicted this would be the
light-lane ticket E3 could not take, but `.claude/heavy-lane-paths.md` makes
*any path matching `*care*`* heavy wherever it lives, and
`frontend/src/routes/care/` matches it literally. Doubt means heavy; the
diff is comments, so the lane costs little. If the lane table's owner wants
a narrower `*care*` row, that is a process PR, not this ticket's call.
**Security-relevant:** no — comments change; no behavior does.

## Context

The carried entry (via `carried-from-e3.md`'s pass-through list, source in
`docs/tickets/e3/carried-from-e2.md`) is precise about what is stale, and it
is not the docstring's account of the component itself — the entry says in
as many words that the assertion the component makes is correct and only the
prose is stale. The false clause is the docstring's claim about the *other*
landings: it says none of the five landings has any motion, a count that
later epics' landing work made wrong. A wrong census of sibling routes on
the Care surface is worth a ticket because the next reader of that file is
likely E10's builder, working on the highest human-review-burden epic in the
plan, and a false orientation there costs review attention exactly where it
is scarcest.

The entry's done-when has two halves and this ticket owes both: the landing
docstring's stale clause corrected, and the stylesheet's opening comment
either left explicitly as dated history or dated in words — the carried
entry's own alternatives.

## Scope

- The docstring's sibling-landings clause made true — verified against the
  actual motion state of each landing route, not against another document's
  description of them.
- The stylesheet's opening comment handled per the done-when's either/or,
  with the choice stated in the diff.
- Nothing else. No code motion, no rename, no tidying the neighborhood.

## Acceptance criteria

1. Every factual claim the docstring makes is checked against the code it
   describes — the sibling-landing census by reading each landing's actual
   motion usage, the component's own claims against its rendered behavior —
   and the diff corrects exactly what was false.
2. The stylesheet comment is dated or marked as history, per the entry.
3. The diff touches only comment blocks — a reviewer can verify the
   no-behavior-change claim by the diff shape alone.
4. The carried entry closes in `carried-from-e3.md` with what closed it,
   both halves named.

## Out of scope

- Everything with a behavior. Any real defect found while verifying the
  docstring gets filed (deferred.md or a carried entry), not fixed here.
