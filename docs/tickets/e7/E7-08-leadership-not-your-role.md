# E7-08 — Leadership pages say "not part of your role"

**ID:** E7-08
**Branch:** `e7/leadership-not-your-role`
**Depends on:** none
**Lane:** heavy
**Why this lane:** it changes `backend/app/api/deps.py`, the dependency chain
every route authenticates through.
**Size:** S
**Security-relevant:** the gate on every leadership route. A defect here admits
a non-leader to a leadership route, or lets a caller tell a forged token from a
real one by the answer.

## Context

The carried entry "A signed-in reader without the role is told their session
ended" (`carried-from-e6.md`). A student or plain instructor who opens a
leadership page reads "This page is not signed in. The session this page was
opened with has ended." That is untrue: they are signed in, in another role.
`require_leadership` answers 401 to every refusal on purpose: absent,
malformed, expired, wrongly signed, and a real session in another role
(`api/deps.py`'s docstrings; no ADR records it). The page reads every 401 as an
ended session.

**Ruling 11.** A real, verified session in another role gets **403**. The first
four cases stay 401, collapsed together as now, so a caller trying tokens still
cannot tell a real one from a forgery. The 403 tells a caller only that the
token they already hold is a real session, which they could learn from the role
it was issued for. The pages read a 403 as "not part of your role" and a 401 as
the ended session.

Only `require_leadership` and `csrf_verified_leadership` change. The student
and instructor gates keep their 401 for every refusal; ADR 0196 says why the
leadership gate differs (it is the only gate a person in another role reaches
from a link in the product).

This ticket also adds its cases to `tests/e2e/leadership-moderation.spec.ts`,
so it takes that spec's two LOWs from E6-06's review: `beforeAll` deletes any
stale test-only `lead_faculty_mapping` row first, and `afterAll` deletes only a
row this run inserted.

Read first: SPEC §2 and §4.1; ADRs 0089, 0098 and 0190; `api/deps.py`'s three
role gates and `_session_in_role`; `frontend/src/api/leadership.ts`.

## Owns

- `backend/app/api/deps.py`: `require_leadership` and `csrf_verified_leadership`
  answer 403 to a verified session in another role.
- `backend/app/api/leadership.py`: the module docstring's paragraph on the 401.
- The backend copy entry for the 403 sentence, beside the leadership gate's
  existing refusal in `backend/app/copy/`.
- `frontend/src/api/leadership.ts`: a `not-your-role` outcome for 403, on every
  call.
- `frontend/src/routes/leadership/` and `frontend/src/copy/leadershipModerationCopy.ts`,
  `leadershipComparisonSetCopy.ts`: the "not part of your role" sentence on the
  review queue, exclusion log and comparison-set pages.
- `tests/e2e/leadership-moderation.spec.ts`: the two cases below and the two
  LOWs.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated if the declared
  responses change.
- ADR **0196**.

## Done when

1. **A signed-in reader in another role gets 403.** A real student session and
   a real instructor session each get 403 from every leadership route, read and
   write, over HTTP against the built application, and the body names no route,
   section or person.
2. **Every other refusal is still one 401.** Absent, malformed, expired and
   wrongly signed tokens each get the same 401 with the same body and headers,
   so none can be told from another. An expired but correctly signed student
   token gets 401, not 403. (Sessions are signed tokens with no server-side
   record, ADR 0089, so no session can be ended on the server; the review's
   wording for that case was dropped when the tests were written.)
3. **A leader is still admitted**, beside each refusal above, in one world.
4. **The two-hat case.** A person with an instructor and a leadership
   assignment gets 403 under the instructor session and is admitted under the
   leadership session.
5. **The pages tell the two apart.** A 403 renders "not part of your role"; a
   401 renders the ended-session sentence; on every leadership page.
6. **Driven both ways.** An e2e case opens the review queue and a
   comparison-set page as a signed-in student and reads the role sentence, and
   opens one with an ended session and reads the ended sentence.
7. **The LOWs are closed.** The spec's cleanup deletes only a row this run
   inserted, and a stale row from a killed run is removed first.
8. **The records match.** ADR 0196 is written and indexed, and `api/deps.py`'s
   and `api/leadership.py`'s docstrings say what the gate now does.

## Shares files with

- `api/leadership.py`: 03 after this merges.
- `frontend/src/api/leadership.ts`: 07 after this merges.
- `openapi.json`, `wire.gen.ts`, `docs/adr/README.md`: 01 and 04 in parallel.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 38, 47 and 53.

## Known traps

- **Entry 47.** Test the status against the built application over HTTP, not by
  calling the dependency.
- **Entry 53.** Check every leadership route, found by the sweep that finds
  routes carrying `require_leadership`, not a hand-written list.

## Not in this ticket

- The student and instructor gates.
- The dean's, assistant dean's and vice president's 403 from the review queue,
  which ADR 0190 already gives them.
