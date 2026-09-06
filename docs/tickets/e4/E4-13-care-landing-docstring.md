# E4-13 — The Care landing docstring

**ID:** E4-13
**Branch:** `e4/care-landing-docstring`
**Depends on:** nothing
**Lane:** heavy — not a typo. E3's record predicted this would be the
light-lane ticket E3 could not take, but `.claude/heavy-lane-paths.md` makes
*any path matching `*care*`* heavy wherever it lives, and
`frontend/src/routes/care/` matches it literally. Doubt means heavy; the
diff is a docstring, so the lane costs little. If the lane table's owner
wants a narrower `*care*` row, that is a process PR, not this ticket's call.
**Security-relevant:** no — a comment changes; no behavior does.

## Context

The carried one-liner: the docstring in `frontend/src/routes/care/index.tsx`
is stale — it describes the landing as something it stopped being. A wrong
comment on the Care surface is worth a ticket because the next reader of
that file is likely to be E10's builder, working on the highest
human-review-burden epic in the plan, and a false orientation there costs
review attention exactly where it is scarcest.

The carried entry's own wording governs what "stale" means; read it via
`carried-from-e3.md`'s pass-through list and the E2-era source entry it
points at.

## Scope

- The docstring says what the Care landing actually is today, and what it
  waits for (E10's queue).
- Nothing else. No code motion, no rename, no tidying the neighborhood.

## Acceptance criteria

1. The docstring is true, checked against the rendered route's actual
   behavior, not against another document's description of it.
2. The diff touches exactly the comment block — a reviewer can verify the
   no-behavior-change claim by the diff shape alone.
3. The carried entry closes in `carried-from-e3.md` with what closed it.

## Out of scope

- Everything with a behavior. Any real defect found while verifying the
  docstring gets filed (deferred.md or a carried entry), not fixed here.
