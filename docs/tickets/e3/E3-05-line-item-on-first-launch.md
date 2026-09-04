# E3-05 — The line item is created on the first staff launch

**ID:** E3-05
**Branch:** `e3/line-item-on-first-launch`
**Depends on:** E3-02, E3-04
**Lane:** heavy
**Security-relevant:** yes. The ticket adds work to the launch door, which is
where a request first authenticates, and it decides which launching role can
cause a write to a platform's gradebook. `backend/app/api/`,
`backend/app/services/` and `backend/app/jobs/` are all heavy lane.

## Context

SPEC §3.4's line item is "created by the tool on first launch", and this is
the ticket that wires that sentence to the door. The pattern already exists
one line over: §7.3's roster trigger says an instructor launch triggers a
roster sync, a leadership launch triggers one only inside the launcher's own
purview, and a student launch triggers nothing. Line-item creation follows
the same rule, and **ruled at breakdown, 2026-09-04**, the student half of it
is not a default but a requirement: a student launch must never cause a write
to the platform's gradebook.

The enqueue shape is the other half of the ticket, and it is a live carried
hazard rather than a style preference. `request_section_sync`
(`backend/app/services/roster_sync.py:674`) publishes on an unbounded
connection, so a staff launch whose broker is restarting holds the request
for six seconds after the launch is already verified and committed. The
bounded shape sits beside it in `enqueue_reclassification`
(`backend/app/services/validity.py:302`), which builds a connection of its
own with retries off and bounded socket timeouts, measured at 0.037 seconds
against a closed port. **This hook uses the bounded shape.**

The carried entry for the unbounded one names its owner as whichever epic
next touches the launch door's suites. That is this ticket, so it takes it:
the six-second wait is fixed here, in the same change that adds a second
enqueue beside it, rather than leaving two shapes on one door.

Read first: SPEC §3.4, §7.3; `carried-from-e2.md`, the six-second enqueue
entry, whose done-when governs; `docs/MISTAKES.md` entry 41, which is the
incident that shape came from; both enqueue functions named above; E3-04's
client.

## Scope

- The creation hook on the launch path: the first qualifying launch of a
  section creates "Pulse Participation" if the section has none, using the
  bounded enqueue and never blocking the launch on the result.
- The trigger rule, mirroring §7.3's: instructor launches trigger creation,
  leadership launches trigger it only inside the launcher's own purview,
  student launches trigger nothing.
- Idempotence: a container that already holds the item does not get a second
  one, whether Pulse created the first or a human did.
- `request_section_sync` moved onto the bounded connection shape, closing the
  carried entry, with the timing test its done-when asks for.

## Acceptance criteria

1. An instructor launch of a section with no line item results in one being
   created; a second launch creates nothing further.
2. A student launch of the same section, before any staff launch, creates
   nothing and writes nothing to the gradebook — asserted against the mock's
   line-item container being empty afterwards, not merely against no task
   being enqueued.
3. A leadership launch outside the launcher's purview creates nothing and
   records the defect §7.3 already defines for the roster case.
4. A section whose launch carried no AGS claim gets no creation attempt and
   the state E3-02 records, not an error.
5. The launch returns promptly with the broker at a closed port — a timing
   assertion under a stated budget, for both the creation enqueue and the
   roster enqueue, because the carried entry's done-when asks for exactly
   that and both now sit on the same door.
6. A container that already holds a "Pulse Participation" item produced by
   something other than Pulse is reconciled to, not duplicated — the rule
   E3-04 settled, exercised from the launch path.

## Decisions this ticket settles

- **Whether creation is enqueued or synchronous.** The recommendation is
  enqueued, on the bounded shape, because the launch has already done its own
  job by the time this runs and a platform that is slow must not be a launch
  that is slow. If it is synchronous instead, the ADR says what bounds it.
- **What a failed creation looks like on the next launch.** Retrying every
  launch and retrying never are both wrong; the rule gets written down.
- **Whether the roster trigger and the gradebook trigger share one decision
  point.** They ask the same question about the same launch, and
  `docs/MISTAKES.md` entry 13 is about answering the same question in two
  places. Routing both through one helper is the default; a reason to keep
  them apart is stated if they stay apart.

## Known traps

- **A student launch that writes to a gradebook is the failure this ticket
  exists to prevent**, and it is easy to write by accident: the natural
  implementation is "on launch, ensure the line item", and the role check is
  the part that gets added second. Write the refusal case first.
- **The six-second hazard is copyable.** A new enqueue written by looking at
  the nearest example will pick up the unbounded connection, because that is
  what the launch door currently contains. Fixing the neighbour in the same
  change is what stops the next one inheriting it (`docs/MISTAKES.md` entry
  13 again).
- **A change that adds a call to a shared entry point is not verified by the
  suites of the ticket that made it** (`docs/MISTAKES.md` entry 41's
  corollary). Run the whole suite and read its timing as well as its result.
- **A verification window equal to the thing's own debounce** proves nothing
  (`docs/MISTAKES.md` entry 7). The roster trigger is debounced; whatever
  timing budget this ticket asserts is chosen against that, not around it.

## Out of scope

- Posting a score — E3-06.
- The development trigger that runs a passback on demand — E3-07.
- Any change to what a launch is allowed to do beyond this one hook.
