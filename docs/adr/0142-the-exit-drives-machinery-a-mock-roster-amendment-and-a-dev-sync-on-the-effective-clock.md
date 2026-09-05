# 0142 — The exit drive's machinery: a mock roster amendment, and a development sync whose call log is on the effective clock

**Status:** Accepted — E3-08.

## Context

SPEC §14.3's exit line for E3 is that "the mock-LMS gradebook shows correct
percentages across enrollment edge cases", and E3-08's first acceptance criterion
requires every row of its exit table to be *driven against the running stack*
rather than asserted in process. Four facts stood between that requirement and a
drive.

**Two of §3.4's enrollment cases are events, not states.** A member who first
appears in a roster sync *later than their section's first* is defined by the
order of two syncs, so no seed can hold it: whatever the seed contains was there
at the first sync. A member who leaves while the drive is watching is the same
shape. Both are things a registrar does to a live section.

**A roster cannot be re-read on a pretended clock.** SPEC §7.3 pulls a roster on
the hour and on a staff launch, and the launch trigger is debounced against that
section's own last call by `DEBOUNCE_WINDOW`, five minutes of **real** time
(`backend/app/services/roster_sync.py`). Neither clock moves when ADR 0109's
development override does, so a drive standing at October cannot make the tool
re-read a roster it read a minute ago.

**The tier-3 comparison crosses two clock currencies.** §3.4 credits a
later-arriving member "from the week of that sync", and the implementation
compares a section's earliest `nrps_call.called_at` (real time — ADR 0109 lists
the call log among the clocks the development override deliberately does not
move) against enrollment dates written from `app.services.clock` (the effective
clock). A drive whose sync rows sit on the real axis therefore gets an answer
that depends on the calendar date it is run on: in September 2026 the pretended
October sync is "later" than a log written today, and a run in November would
read the same rows the other way round.

**The mock platform's third section could not be launched at all.** `mock-lms`
seeds `NURS-8100-Q2FF`, which holds the only member the platform never dated
(§3.4's undated tier) and is where the later-sync case belongs; Pulse's demo
institution seeded no `NURS` prefix, so a launch from it was refused as an
`unknown_prefix` defect and provisioned nothing. E2 recorded the gap in a spec
comment and worked around it by using other sections; an exit proof whose own
table names that section's windowless member cannot.

## Decision

Four pieces, all development-only or mock-only.

1. **`POST /mock/roster-amendments`** on the mock platform, in ADR 0047's
   `/mock/` namespace and tokenless for that namespace's reason (ADR 0134): no
   real platform serves it, so there is no scope a tool could hold. Two actions —
   `add` enrolls `app.seed.student(context, ordinal)` `Active` and **undated**
   (201), `drop` rewrites an enrollment `Inactive` with the instant the caller
   supplies (200). Refusals: `400` for a body that is not a JSON object, `422`
   for one this route cannot read as an amendment, `404` for an unseeded section
   or a member the section does not hold, `409` for an ordinal it already holds.
   The amendment mutates the `SeededPlatform` instance the process serves from,
   which is why that class is no longer frozen; there is no reset action, because
   CI seeds a fresh stack per run and a local re-run re-seeds.
2. **`POST /dev/roster-sync`**, a `DevControlRoute` exactly like E3-07's passback
   trigger (ADR 0141) — development-only, `POST`-only through the route class, a
   same-origin `Origin` check, `303` back to the console, and a button beside the
   other one. It runs `sync_all_rosters` synchronously in the request and commits,
   which is the hourly task's own arrangement.
3. **The call rows that control writes carry the effective clock.**
   `sync_section`, `sync_all_rosters` and `_record_call` take an optional
   `called_at`; every production caller omits it and gets `datetime.now(UTC)`.
   The development control reads `clock.now` once and passes it, which bounds a
   drive's `first_sync_day` at the first dev-sync instant and makes every tier
   deterministic whatever the real date is.
4. **`NURS` is seeded as a prefix** in `scripts/seed.py`, grouped under the
   Biology department. The course is not seeded: a launch upserts the course it
   names, so `NURS 8100` arrives with the platform's own title.

## Alternatives rejected

**Wait the debounce out.** Five real minutes of sleep per sync, at four sync
points, in a gate CI runs on every pull request — and `docs/MISTAKES.md` entry 7
is this project's record of what a verification window equal to the thing's own
debounce buys.

**Widen the launch page's cast so a per-section student can launch and trigger
the sync that way.** It changes the seeded world every other suite reads, still
carries the debounce, and misstates the case: what happens to a roster between
two syncs is something a registrar does, not something a student does by opening
the tool.

**Prove tier 3 in the in-process integration suite only.** That suite already
holds the formula's cases; criterion 1 asks for *every row against the running
stack*, because the exit is about the gradebook a platform holds rather than the
number a service computed.

**Stamp every `nrps_call` on the effective clock.** It would move an
observability instant in production — a §6.1 console answering "when was this
section called" with a pretended time — which is exactly what ADR 0109 lists this
log as exempt from.

**Thread a clock through `roster_sync`.** A movable clock inside a service ADR
0109 keeps real is a standing invitation to read it somewhere else; an optional
instant on the entry point is the whole of what the exception needs, and it is
`None` on every path a deployment runs.

**A reset action on the mock.** Its state is per process, so a reset would exist
to make a drive re-runnable against a stack that has already been driven — a
promise the platform cannot honestly keep for the Pulse database beside it.

**A Nursing department of its own for the `NURS` prefix.** Every seeded
department carries a chair, so a new one needs a person invented whose only
purpose is to chair a prefix the demo seeds no course in. Grouping it under
Biology leaves the people graph exactly as it was and keeps SPEC §2.1's
"department groups one or more prefixes" true of a second department.

## Consequences

- **A development stack's `nrps_call` log is now written in two currencies**: the
  rows this control wrote carry the effective clock and every other row carries
  real time. That is visible to anyone reading the log by hand on a stack whose
  clock has been moved, and it is the price of a deterministic drive; the handler
  and `_record_call` both say so.
- **The exit spec must run after every other end-to-end spec**, because it moves
  the clock across six weeks and makes two roster amendments the stack cannot
  undo. `playwright.config.ts` splits it into a `grade-passback-exit` project
  that `dependencies` orders after the main one, and the main project ignores the
  file. The ordering claim is only proven by a run of the whole suite.
- **The mock platform can now be written to without a credential**, on a service
  that exists only in the development Compose stack and whose whole state is one
  process's seed. The blast radius is that seed; the route can create no course,
  no section and no person outside it.
- **`SeededPlatform` is mutable.** The four record classes it holds stay frozen,
  so what an amendment changes is which enrollments the platform holds and never
  what one of them says.
- **Pulse's demo institution holds a prefix with no seeded course** until
  somebody launches from the mock's nursing section, at which point the launch
  writes one.
